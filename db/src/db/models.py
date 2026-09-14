"""The eight tables (GP-plan §5.2).

Types are chosen so the same models run on PostgreSQL (dev, CI, Supabase) and on
SQLite (the API's isolated unit tests): `Uuid`, and JSON that becomes JSONB on Postgres.

Enum values are duplicated from `contracts.run` on purpose — `db` depends on nothing.
`api/tests/test_enums_match_contracts.py` fails the build if they drift.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NODE_STATUSES = ("pending", "running", "retrying", "awaiting_approval", "success", "failed", "skipped")
RUN_STATUSES = ("queued", "running", "awaiting_approval", "succeeded", "failed", "cancelled")
OUTPUT_TYPES = ("text", "file", "url")
APPROVAL_DECISIONS = ("approve", "reject")
MAX_RETRIES = 3

JSONType = JSON().with_variant(JSONB(), "postgresql")

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    """Mirrors Supabase `auth.users` (id = the JWT `sub`)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = _now()


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    graph_definition: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AgentNode(Base):
    """One row per node on a canvas. Derived from `graph_definition` on every save.

    `agent_type` is text, not a Postgres enum, so a new agent (AT-12) needs no migration.
    """

    __tablename__ = "agent_nodes"
    __table_args__ = (UniqueConstraint("workflow_id", "position_order", name="uq_agent_nodes_workflow_position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    position_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ExecutionRun(Base):
    """One row per Run press — the unit NFR-02 is measured over."""

    __tablename__ = "execution_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        Enum(*RUN_STATUSES, name="run_status"), nullable=False, default="queued", server_default="queued"
    )
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    total_nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExecutionLog(Base):
    """One row per node execution, updated in place through its status transitions.

    `node_id` references a node in the run's `graph_snapshot` (not `agent_nodes`), so
    history survives later edits to the workflow.
    """

    __tablename__ = "execution_logs"
    __table_args__ = (
        UniqueConstraint("run_id", "node_id", name="uq_execution_logs_run_node"),
        CheckConstraint(f"retry_count >= 0 AND retry_count <= {MAX_RETRIES}", name="retry_count_range"),
        Index("ix_execution_logs_run_started", "run_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    position_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        Enum(*NODE_STATUSES, name="node_status"),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    output_type: Mapped[str] = mapped_column(Enum(*OUTPUT_TYPES, name="output_type"), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    storage_path: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(127))
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()


class Credential(Base):
    """Google OAuth tokens, encrypted. Never stored in a workflow's configuration."""

    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class Approval(Base):
    """The UC-04 audit trail."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("execution_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(Enum(*APPROVAL_DECISIONS, name="approval_decision"), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime] = _now()
    note: Mapped[str | None] = mapped_column(Text)
