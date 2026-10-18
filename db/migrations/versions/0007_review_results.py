"""Reviewing a step's result: redo it with a note, or edit it, before the next step runs.

A step can now wait for a person *after* it runs, with its result: they approve it (as it is or
edited), reject it, or send it back with a note to be done again ("redo"). Each redo makes a new
result, reviewed in its turn, so a step can be decided more than once — once per result:

- execution_logs.revision: how many times the step's result was sent back (0 for the first result).
- approvals.revision: which result a decision was on. (log_id, revision) is unique, replacing
  0004's one-decision-per-step (log_id): a double-submitted click is still refused.
- approvals.edited: the person changed the result's text before approving it.
- approval_decision gains "redo".

Downgrade restores one decision per step. It refuses — rather than choose which decisions to
delete — when a step has more than one, or a decision is a redo.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new enum value can't be used in the transaction that adds it, and nothing here uses it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE approval_decision ADD VALUE IF NOT EXISTS 'redo'")
    op.add_column("execution_logs", sa.Column("revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("approvals", sa.Column("revision", sa.Integer(), server_default="0", nullable=False))
    op.add_column("approvals", sa.Column("edited", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.drop_constraint("uq_approvals_log_id", "approvals", type_="unique")
    op.create_unique_constraint("uq_approvals_log_revision", "approvals", ["log_id", "revision"])


def downgrade() -> None:
    bind = op.get_bind()
    repeated = bind.scalar(
        sa.text(
            "SELECT count(*) FROM (SELECT 1 FROM approvals GROUP BY log_id HAVING count(*) > 1) AS steps"
        )
    )
    redone = bind.scalar(sa.text("SELECT count(*) FROM approvals WHERE decision = 'redo'"))
    if repeated or redone:
        raise RuntimeError(
            f"Can't downgrade: {repeated} step(s) were decided more than once and {redone} decision(s) are "
            "redos, which 0006 can't record. Nothing was changed."
        )
    op.drop_constraint("uq_approvals_log_revision", "approvals", type_="unique")
    op.create_unique_constraint("uq_approvals_log_id", "approvals", ["log_id"])
    op.drop_column("approvals", "edited")
    op.drop_column("approvals", "revision")
    op.drop_column("execution_logs", "revision")
    # PostgreSQL can't drop one value from an enum: the type is made again without it.
    op.execute("ALTER TYPE approval_decision RENAME TO approval_decision_0007")
    op.execute("CREATE TYPE approval_decision AS ENUM ('approve', 'reject')")
    op.execute(
        "ALTER TABLE approvals ALTER COLUMN decision TYPE approval_decision "
        "USING decision::text::approval_decision"
    )
    op.execute("DROP TYPE approval_decision_0007")
