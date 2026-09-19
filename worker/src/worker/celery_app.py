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

from adapters.factory import AdapterSettings, build_ports
from contracts.queue import CATALOG_REDIS_KEY, RUN_WORKFLOW_TASK
from db.session import make_engine, make_session_factory
from worker.orchestrator import Orchestrator
from worker.registry import Registry
from worker.settings import get_settings
from worker.store import SqlRunStore

log = logging.getLogger(__name__)
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


def registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry.from_entry_points()
    return _registry


def store() -> SqlRunStore:
    global _store
    if _store is None:
        _store = SqlRunStore(make_session_factory(make_engine(settings.database_url)), settings.storage_root)
    return _store


def publish_catalog() -> int:
    """Write the agent catalog where the API can read it, without the API importing any agent."""
    catalog = [m.model_dump(mode="json") for m in registry().catalog()]
    redis.Redis.from_url(settings.redis_url).set(CATALOG_REDIS_KEY, json.dumps(catalog))
    return len(catalog)


@worker_ready.connect
def _on_ready(**_: object) -> None:
    count = publish_catalog()
    log.info("published %d agents to %s", count, CATALOG_REDIS_KEY)


@app.task(name=RUN_WORKFLOW_TASK)
def run_workflow(run_id: str) -> str:
    ports = build_ports(
        AdapterSettings(
            fake=settings.fake_adapters,
            storage_root=settings.storage_root,
            public_base_url=settings.public_files_url,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            search_api_key=settings.search_api_key,
        )
    )
    run_store = store()
    run_store.mark_interrupted(UUID(run_id))
    status = asyncio.run(Orchestrator(run_store, registry(), ports).execute(UUID(run_id)))
    log.info("run %s finished with status %s", run_id, status)
    return status.value
