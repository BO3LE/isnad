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

from adapters.factory import MisconfiguredLLM, build_llm, build_ports, llm_provider
from contracts.queue import CATALOG_REDIS_KEY, RUN_WORKFLOW_TASK
from db.crypto import CredentialCipher, CredentialKeyError
from db.session import make_engine, make_session_factory
from worker.credentials import CredentialPorts, CredentialResolver, GoogleClient
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
    return CredentialPorts(ports, CredentialResolver(sessions(), cipher, google))


def publish_catalog() -> int:
    """Write the agent catalog where the API can read it, without the API importing any agent."""
    catalog = [m.model_dump(mode="json") for m in registry().catalog()]
    redis.Redis.from_url(settings.redis_url).set(CATALOG_REDIS_KEY, json.dumps(catalog))
    return len(catalog)


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
    if not result["reachable"]:
        return f"LLM: {where} — server not reachable ({result.get('error')})"
    if not result["model_listed"]:
        return f"LLM: {where} — server up, but it doesn't list that model (it lists: {result.get('models')})"
    return f"LLM: {where} — ready"


@worker_ready.connect
def _on_ready(**_: object) -> None:
    count = publish_catalog()
    log.info("published %d agents to %s", count, CATALOG_REDIS_KEY)
    try:
        log.info(check_llm())
    except Exception as exc:  # a startup report must never stop the worker
        log.warning("LLM: couldn't check (%s)", type(exc).__name__)


@app.task(name=RUN_WORKFLOW_TASK)
def run_workflow(run_id: str) -> str:
    ports = build_ports(adapter_settings(settings))
    run_store = store()
    run_store.mark_interrupted(UUID(run_id))
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
