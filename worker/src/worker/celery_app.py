"""Celery entry point.

    celery -A worker.celery_app worker --loglevel=INFO

The job payload is a run id and nothing else (GP-plan C2). Everything the worker needs
is loaded from the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import redis
from celery import Celery
from celery.signals import worker_ready

from adapters.email.smtp import SmtpEmail
from adapters.factory import (
    MisconfiguredEmail,
    MisconfiguredLLM,
    MisconfiguredSearch,
    build_email,
    build_llm,
    build_ports,
    build_search,
    connection_ports,
    llm_provider,
)
from adapters.search.fake import FakeSearch
from contracts.manifest import AgentManifest
from contracts.queue import CATALOG_REDIS_KEY, RUN_WORKFLOW_TASK
from db.crypto import CredentialCipher, CredentialKeyError
from db.session import make_engine, make_session_factory
from worker.credentials import (
    CredentialPorts,
    CredentialResolver,
    GoogleClient,
    credential_port_of,
    mark_unused_connections,
)
from worker.orchestrator import Orchestrator
from worker.registry import Registry
from worker.settings import adapter_settings, get_settings
from worker.store import SqlRunStore

log = logging.getLogger(__name__)
# httpx logs every request URL at INFO; held to warnings, as in the API (api/logs.py).
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
settings = get_settings()

app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_acks_late=True,  # RB-01: a job is only acknowledged once it finishes
    task_reject_on_worker_lost=True,  # …and is redelivered if the worker dies mid-run
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

_registry: Registry | None = None
_store: SqlRunStore | None = None
_sessions = None


def registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry.from_entry_points()
    return _registry


def sessions():
    global _sessions
    if _sessions is None:
        _sessions = make_session_factory(make_engine(settings.database_url))
    return _sessions


def store() -> SqlRunStore:
    global _store
    if _store is None:
        # File sizes are read from the local disk, so only when files are written there.
        local_root = settings.storage_root if settings.storage_backend == "local" else None
        _store = SqlRunStore(sessions(), local_root)
    return _store


def credential_ports(ports):
    """Per-node Google ports (D-09). None in fake mode: the fakes need no Google setup at all."""
    if settings.fake_adapters:
        return None
    try:
        cipher = CredentialCipher(settings.credentials_encryption_key)
    except CredentialKeyError:
        cipher = None  # a node that names an account then fails with a readable "not set up" message
    google = (
        GoogleClient(settings.google_client_id, settings.google_client_secret)
        if settings.google_client_id and settings.google_client_secret
        else None
    )
    return CredentialPorts(
        ports,
        CredentialResolver(sessions(), cipher, google),
        ports=connection_ports(adapter_settings(settings)),
        port_of=credential_port_of(registry().catalog()),
    )


def published_catalog() -> list[AgentManifest]:
    """The catalog as this worker runs it: in real mode, an account field this server won't use
    (Email over SMTP) is marked so, and the API doesn't ask for a Google connection there."""
    manifests = registry().catalog()
    if settings.fake_adapters:
        return manifests
    used = connection_ports(adapter_settings(settings))
    return [mark_unused_connections(m, used) for m in manifests]


def publish_catalog() -> int:
    """Write the agent catalog where the API can read it, without the API importing any agent."""
    catalog = [m.model_dump(mode="json") for m in published_catalog()]
    redis.Redis.from_url(settings.redis_url).set(CATALOG_REDIS_KEY, json.dumps(catalog))
    return len(catalog)


def check_email() -> str:
    """One line on where the Email step's messages go. Names the host only — never a password."""
    if settings.fake_adapters:
        return "Email: fake (FAKE_ADAPTERS=true)"
    email = build_email(adapter_settings(settings))
    if isinstance(email, MisconfiguredEmail):
        return f"Email: not usable — {email.message}"
    if isinstance(email, SmtpEmail):
        where = f"{email.config.host}:{email.config.port}"
        caught = (
            " (Mailpit catches every message: http://localhost:8025)"
            if email.config.host in ("mailpit", "localhost", "127.0.0.1")
            else ""
        )
        return f"Email: smtp to {where}{caught}"
    return "Email: gmail, through the Google account each Email step names"


def check_llm() -> str:
    """One line on the LLM the Writer will use: provider, model, and whether the server answers.

    Logged at startup so a stopped LM Studio shows up before the first run, not during it.
    Names the provider, model and base URL only — never a key.
    """
    if settings.fake_adapters:
        return "LLM: fake (FAKE_ADAPTERS=true)"
    adapter_cfg = adapter_settings(settings)
    llm = build_llm(adapter_cfg)
    if isinstance(llm, MisconfiguredLLM):
        return f"LLM: not usable — {llm.message}"
    probe = getattr(llm, "probe", None)
    config = getattr(llm, "config", None)
    if probe is None or config is None:
        return f"LLM: {llm_provider(adapter_cfg)}"
    result = asyncio.run(probe())
    where = f"{config.provider} model {config.model!r} at {config.base_url}"
    if getattr(config, "reasoning_effort", None):
        where += f", reasoning_effort={config.reasoning_effort}"
    if not result["reachable"]:
        return f"LLM: {where} — server not reachable ({result.get('error')})"
    if not result["model_listed"]:
        return f"LLM: {where} — server up, but it doesn't list that model (it lists: {result.get('models')})"
    return f"LLM: {where} — ready"


def check_search() -> str:
    """One line on where the Researcher's sources come from. No request is made: a search costs a credit."""
    if settings.fake_adapters:
        return "Search: fake (FAKE_ADAPTERS=true)"
    search = build_search(adapter_settings(settings))
    if isinstance(search, MisconfiguredSearch):
        return f"Search: not usable — {search.message}"
    if isinstance(search, FakeSearch):
        return "Search: fake (SEARCH_PROVIDER=fake) — the Researcher's sources are made up"
    return "Search: tavily"


def check_image() -> str:
    if settings.fake_adapters:
        return "Image: fake (FAKE_ADAPTERS=true)"
    return "Image: fake — there is no real image adapter yet; the Image step makes placeholders"


@worker_ready.connect
def _on_ready(**_: object) -> None:
    count = publish_catalog()
    log.info("published %d agents to %s", count, CATALOG_REDIS_KEY)
    for name, check in (
        ("LLM", check_llm),
        ("Search", check_search),
        ("Image", check_image),
        ("Email", check_email),
    ):
        try:
            log.info(check())
        except Exception as exc:  # a startup report must never stop the worker
            log.warning("%s: couldn't check (%s)", name, type(exc).__name__)


@app.task(name=RUN_WORKFLOW_TASK)
def run_workflow(run_id: str) -> str:
    ports = build_ports(adapter_settings(settings))
    run_store = store()
    run_store.mark_interrupted(UUID(run_id), unrepeatable=registry().sends_out())
    orchestrator = Orchestrator(
        run_store,
        registry(),
        ports,
        ports_for=credential_ports(ports),
        step_timeout_s=settings.step_timeout_s or None,
    )
    status = asyncio.run(orchestrator.execute(UUID(run_id)))
    log.info("run %s finished with status %s", run_id, status)
    return status.value
