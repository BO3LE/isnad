"""Enqueue runs. The API pushes a task *by name* carrying only the run id — it never imports the worker."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from celery import Celery

from contracts.queue import RUN_WORKFLOW_TASK


class Enqueuer(Protocol):
    def enqueue_run(self, run_id: UUID) -> None: ...


class CeleryEnqueuer:
    def __init__(self, broker_url: str):
        self._celery = Celery("api", broker=broker_url)

    def enqueue_run(self, run_id: UUID) -> None:
        self._celery.send_task(RUN_WORKFLOW_TASK, args=[str(run_id)])
