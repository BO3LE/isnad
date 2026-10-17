"""Credentials: one connection per Google account *and access* (D-09).

Google won't grant YouTube and Drive in one consent ("This request contains scopes that cannot be
requested together", Error 400 invalid_request), so a Google account is connected once for YouTube
and once for Drive and Gmail (api/google_oauth.py). Each is its own row with its own refresh token.

- access: `youtube` or `drive_gmail`; rows from before the split are `all`.
- the unique key becomes (user, provider, account, access): reconnecting the same access of the
  same account still updates its row in place, so workflows that reference its id keep working.

Downgrade restores one row per account. It refuses — rather than choose which connection to
delete — when an account has more than one.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Server default only to backfill existing rows, then dropped: the application sets it.
    op.add_column("credentials", sa.Column("access", sa.String(length=16), server_default="all", nullable=False))
    op.alter_column("credentials", "access", server_default=None)
    op.drop_constraint("uq_credentials_user_provider_account", "credentials", type_="unique")
    op.create_unique_constraint(
        "uq_credentials_user_provider_account_access",
        "credentials",
        ["user_id", "provider", "account_email", "access"],
    )


def downgrade() -> None:
    shared = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM (SELECT 1 FROM credentials GROUP BY user_id, provider, account_email"
            " HAVING count(*) > 1) AS accounts"
        )
    )
    if shared:
        raise RuntimeError(
            f"{shared} Google account(s) have more than one connection (YouTube and Drive · Gmail). "
            "Disconnect one of each in Settings → Connections, then downgrade again."
        )
    op.drop_constraint("uq_credentials_user_provider_account_access", "credentials", type_="unique")
    op.create_unique_constraint(
        "uq_credentials_user_provider_account", "credentials", ["user_id", "provider", "account_email"]
    )
    op.drop_column("credentials", "access")
