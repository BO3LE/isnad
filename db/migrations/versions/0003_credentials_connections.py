"""Credentials: the columns the Connections screen needs (D-09, PROPOSED).

- account_email: which Google account, shown on S-09 and in the credential picker.
- scopes: what the user actually granted (Google lets them untick a scope on the consent screen).
- invalid_at: set when Google answers invalid_grant, so the UI can say "Reconnect".
- updated_at: last refresh or reconnect.
- one row per (user, provider, account): reconnecting the same account updates it in place, so
  workflows that reference its id keep working.

The tokens themselves stay in encrypted_payload (Fernet, see db/crypto.py).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # Server defaults only to backfill any existing rows, then dropped: the application sets both.
    op.add_column(
        "credentials", sa.Column("account_email", sa.String(length=320), server_default="", nullable=False)
    )
    op.add_column("credentials", sa.Column("scopes", JSONType, server_default=sa.text("'[]'"), nullable=False))
    op.add_column("credentials", sa.Column("invalid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "credentials",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.alter_column("credentials", "account_email", server_default=None)
    op.alter_column("credentials", "scopes", server_default=None)
    op.create_unique_constraint(
        "uq_credentials_user_provider_account", "credentials", ["user_id", "provider", "account_email"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_credentials_user_provider_account", "credentials", type_="unique")
    op.drop_column("credentials", "updated_at")
    op.drop_column("credentials", "invalid_at")
    op.drop_column("credentials", "scopes")
    op.drop_column("credentials", "account_email")
