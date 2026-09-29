"""Why a run ended, when its status cannot say.

A run the reviewer stopped and a run that crashed are both `failed`, so the workflow list called
both "Failed". A rejection is a person's own decision and must never be reported as a failure
(DESIGN-SYSTEM.md §16), so the list needs to tell them apart without opening the run.

The worker records a rejection as a failed step carrying `REJECTED_BY_REVIEWER`. It also *appends*
one line per attempt, each prefixed "[attempt N] " (worker/store.py), so the last line is the one
that ended the step — a step that failed once and was then rejected still reads as a rejection.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts.run import REJECTED_BY_REVIEWER
from db.models import ExecutionLog

_ATTEMPT = re.compile(r"^\[attempt \d+\]\s*")


def last_attempt(message: str | None) -> str | None:
    """The attempt that actually stopped the step, without the store's bookkeeping prefix."""
    if not message:
        return None
    lines = [_ATTEMPT.sub("", line).strip() for line in message.splitlines()]
    kept = [line for line in lines if line]
    return kept[-1] if kept else None


def rejected_runs(session: Session, run_ids: Iterable[UUID]) -> set[UUID]:
    """Which of these runs a person stopped. One query, so a list of runs stays one round trip."""
    ids = list(run_ids)
    if not ids:
        return set()
    rows = session.execute(
        select(ExecutionLog.run_id, ExecutionLog.error_message).where(
            ExecutionLog.run_id.in_(ids), ExecutionLog.error_message.is_not(None)
        )
    ).all()
    return {run_id for run_id, message in rows if last_attempt(message) == REJECTED_BY_REVIEWER}
