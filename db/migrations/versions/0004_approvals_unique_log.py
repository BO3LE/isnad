"""One decision per node (W7): `approvals.log_id` becomes unique.

A node parks for approval once and is decided once — the orchestrator (`worker/orchestrator.py`)
never sends a node back to `awaiting_approval` after a decision is recorded, so a second row
against the same `log_id` would only ever be a bug (e.g. a double-submitted approve click), never
a legitimate re-review. The API's read side (`GET /runs/{id}`, `GET /runs/{id}/approvals`) now
surfaces the decision, so this closes the gap before it can produce a confusing audit trail.

Replaces the plain index `ix_approvals_log_id` from 0001 with a unique one — no redundant index.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_approvals_log_id"), table_name="approvals")
    op.create_unique_constraint("uq_approvals_log_id", "approvals", ["log_id"])


def downgrade() -> None:
    op.drop_constraint("uq_approvals_log_id", "approvals", type_="unique")
    op.create_index(op.f("ix_approvals_log_id"), "approvals", ["log_id"], unique=False)
