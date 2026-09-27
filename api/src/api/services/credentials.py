"""Credentials as the rest of the API sees them: references, status, and the no-secrets guard (D-09)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts.run import CREDENTIAL_CONFIG_KEY, WorkflowGraph
from db.models import Credential, Workflow

EXPIRING_WITHIN = timedelta(days=7)

Status = Literal["connected", "expiring", "expired"]

# Shapes of Google secrets, so one pasted into a text field is refused before it is ever stored:
# access tokens (ya29.…), refresh tokens (1//…), OAuth client secrets (GOCSPX-…).
_SECRET_PATTERNS = re.compile(r"(ya29\.[0-9A-Za-z_\-]{20,}|\b1//0[0-9A-Za-z_\-]{20,}|GOCSPX-[0-9A-Za-z_\-]{10,})")
_SECRET_KEYS = {"access_token", "refresh_token", "client_secret", "id_token", "token", "password", "api_key"}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def status_of(row: Credential, now: datetime | None = None) -> Status:
    now = now or datetime.now(UTC)
    expires_at = _utc(row.expires_at)
    if row.invalid_at is not None or (expires_at is not None and expires_at <= now):
        return "expired"
    if expires_at is not None and expires_at - now <= EXPIRING_WITHIN:
        return "expiring"
    return "connected"


def credential_refs(graph: WorkflowGraph | dict[str, Any]) -> Iterator[tuple[UUID, str]]:
    """(node id, referenced credential id) for every step that names an account."""
    if isinstance(graph, dict):
        graph = WorkflowGraph.model_validate(graph or {})
    for node in graph.nodes:
        value = node.configuration.get(CREDENTIAL_CONFIG_KEY)
        if value:
            yield node.id, str(value)


def usage_counts(session: Session, user_id: UUID) -> Counter[str]:
    """How many of this user's workflows reference each credential id (a workflow counts once)."""
    counts: Counter[str] = Counter()
    for definition in session.scalars(select(Workflow.graph_definition).where(Workflow.user_id == user_id)):
        counts.update({ref for _, ref in credential_refs(definition or {})})
    return counts


def user_credentials(session: Session, user_id: UUID) -> dict[str, Credential]:
    rows = session.scalars(select(Credential).where(Credential.user_id == user_id)).all()
    return {str(row.id): row for row in rows}


def secrets_in(graph: WorkflowGraph) -> list[UUID]:
    """Steps whose configuration holds something that looks like a secret (Invariant 4)."""

    def walk(value: Any) -> bool:
        if isinstance(value, str):
            return bool(_SECRET_PATTERNS.search(value))
        if isinstance(value, dict):
            return any(k.lower() in _SECRET_KEYS or walk(v) for k, v in value.items())
        if isinstance(value, list):
            return any(walk(v) for v in value)
        return False

    offenders = [node.id for node in graph.nodes if walk(node.configuration)]
    for node in graph.nodes:
        ref = node.configuration.get(CREDENTIAL_CONFIG_KEY)
        if ref is not None and not _is_uuid(ref) and node.id not in offenders:
            offenders.append(node.id)
    return offenders


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
    except ValueError:
        return False
    return isinstance(value, str)
