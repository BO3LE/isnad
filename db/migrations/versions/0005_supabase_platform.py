"""Supabase platform setup as code (W7-12, D-01): Realtime publication + Storage bucket.

Two things about the Supabase *platform* (not the schema) that GP-plan D-01 and the credentials
work (0003) depend on, brought under migrations so the CD/DVD's "reproducible from `alembic
upgrade head`" claim (SETUP.md §5) also covers them:

1. Realtime — GP-plan D-01 wants live run status pushed to the frontend instead of (or alongside)
   the current 2s poll. Realtime only streams changes for tables added to the `supabase_realtime`
   publication, and RLS SELECT policies for `authenticated` already exist on `execution_runs` and
   `execution_logs` (migration 0002), so adding them here is safe to ship ahead of the frontend
   actually subscribing (Hasan's W3 task) — nothing listens until the frontend opts in, and once it
   does, each user's socket only ever sees rows their own RLS policies already let them read.
   `credentials` and every other table are deliberately left out of the publication.

   REPLICA IDENTITY: left at the Postgres default (primary key). That's enough for Realtime's
   INSERT and UPDATE payloads (both carry the changed row's primary key and, on UPDATE, either
   the full new row or enough to look it up) — the two events this feature needs. Nothing here
   deletes `execution_runs`/`execution_logs` rows, so `REPLICA IDENTITY FULL` (needed for useful
   DELETE payloads) is not worth the extra WAL volume it would cost on every update.

2. Storage — the private bucket `artifacts` (`STORAGE_BUCKET` in SETUP.md §6) was created by hand
   in the Supabase dashboard, which the GP-plan flags as not reproducible for the CD/DVD. This
   migration creates it in code instead, `ON CONFLICT DO UPDATE SET public = false` so re-running
   it (or finding it already there from the hand-made setup) is idempotent and always leaves it
   private. File size and mime-type limits are left NULL (unrestricted) — the API and worker are
   the only writers (`STORAGE_BACKEND=supabase` in SETUP.md §6) and already know what they upload;
   nothing here has a concrete number to enforce and a wrong guess would just break uploads.

Both blocks are guarded and are a no-op on plain Postgres (local Docker, CI): there is no
`supabase_realtime` publication and no `storage` schema outside Supabase.

Downgrade removes `execution_runs`/`execution_logs` from the publication (guarded the same way)
but does NOT delete the `artifacts` bucket — by the time this would ever be downgraded for real,
it may hold uploaded user files, and dropping a Storage bucket is exactly the kind of destructive,
hand-run action this migration exists to avoid encoding.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REALTIME_TABLES = ("execution_runs", "execution_logs")


def _add_to_publication(table: str) -> str:
    return f"""
          IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
            WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = '{table}'
          ) THEN
            EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.{table}';
          END IF;"""


def _drop_from_publication(table: str) -> str:
    return f"""
          IF EXISTS (
            SELECT 1 FROM pg_publication_tables
            WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = '{table}'
          ) THEN
            EXECUTE 'ALTER PUBLICATION supabase_realtime DROP TABLE public.{table}';
          END IF;"""


def upgrade() -> None:
    adds = "".join(_add_to_publication(t) for t in REALTIME_TABLES)
    op.execute(
        f"""
        DO $realtime$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        {adds}
          END IF;
        END
        $realtime$;
        """
    )

    op.execute(
        """
        DO $storage$
        BEGIN
          IF to_regclass('storage.buckets') IS NOT NULL THEN
            INSERT INTO storage.buckets (id, name, public)
            VALUES ('artifacts', 'artifacts', false)
            ON CONFLICT (id) DO UPDATE SET public = false;
          END IF;
        END
        $storage$;
        """
    )


def downgrade() -> None:
    drops = "".join(_drop_from_publication(t) for t in REALTIME_TABLES)
    op.execute(
        f"""
        DO $realtime$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        {drops}
          END IF;
        END
        $realtime$;
        """
    )
    # The `artifacts` bucket is intentionally NOT dropped here — see the module docstring.
