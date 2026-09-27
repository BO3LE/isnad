"""Row Level Security — each user sees only their own workflows (GP-plan §5.2, W2).

What this does (see docs/DECISIONS.md, INF-12):

1. Enables RLS on the eight app tables and on `alembic_version`. With RLS on and no
   policy, every role that is not the table owner (and not BYPASSRLS) sees nothing.
2. On Supabase only, adds per-user policies for the `authenticated` role keyed on
   `auth.uid()`. There are no policies for `anon`, so anonymous PostgREST/Realtime
   access is denied on every table.
3. On Supabase only, revokes EXECUTE on the hand-made `public.rls_auto_enable()`
   (SECURITY DEFINER) from public/anon/authenticated — the security advisor flags it.

Why enabling RLS does not affect the backend: the API (api/src/api/deps.py) and the
worker (worker/src/worker/celery_app.py) both connect through `db.session.make_engine`
with `DATABASE_URL`, i.e. as `postgres` — the role that runs these migrations and so
OWNS every table. A table owner bypasses RLS unless `FORCE ROW LEVEL SECURITY` is set,
which this migration deliberately does not do (on Supabase `postgres` also has
BYPASSRLS). The backend keeps doing its own ownership checks (`api.deps.owned`); the
policies are defence in depth for anything that talks to Supabase directly with a user's
JWT — PostgREST with the anon key, and Realtime subscriptions.

Portability: local docker Postgres and CI have no `auth` schema and no `authenticated`
role, so steps 2 and 3 run inside DO blocks that check for them first and are no-ops
otherwise. Step 1 is plain SQL and runs everywhere.

`credentials` deliberately gets NO policy for `authenticated`: the rows hold encrypted
OAuth tokens that only the backend reads and writes, and the frontend never needs them
(connection status comes from the API). Deny-all is the smallest possible surface.

Downgrade drops every policy. It disables RLS only on plain Postgres (no `auth.uid()`
in this database): on Supabase the
tables had RLS enabled by hand before this migration existed, and turning it off there
would expose every table to the anon key through PostgREST's default grants. For the
same reason the revoke on `rls_auto_enable()` is not undone.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_TABLES = (
    'users',
    'workflows',
    'agent_nodes',
    'execution_runs',
    'execution_logs',
    'agent_outputs',
    'credentials',
    'approvals',
)
RLS_TABLES = (*APP_TABLES, 'alembic_version')

# True only on Supabase (or a database set up to look like it).
_SUPABASE = "to_regprocedure('auth.uid()') IS NOT NULL AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')"

# `(SELECT auth.uid())` rather than `auth.uid()`: evaluated once per statement, not per
# row (Supabase's auth_rls_initplan advisor).
_UID = '(SELECT auth.uid())'
_OWNS_WORKFLOW = f'EXISTS (SELECT 1 FROM public.workflows w WHERE w.id = {{col}} AND w.user_id = {_UID})'
_OWNS_LOG = (
    'EXISTS (SELECT 1 FROM public.execution_logs l JOIN public.workflows w ON w.id = l.workflow_id '
    f'WHERE l.id = {{col}} AND w.user_id = {_UID})'
)

# (table, command, predicate). Coverage is chosen to match what a user may do in the UI:
# - users: read and update your own profile row; the API creates it on first sign-in.
# - workflows, agent_nodes: full CRUD on your own — the builder edits these.
# - execution_runs/logs, agent_outputs, approvals: read-only. Runs are created by the API
#   (which also enqueues them) and written by the worker; an approval decision must go
#   through the API so the paused run is resumed. Reads cover Realtime progress updates.
# - credentials: nothing (see module docstring).
POLICIES: tuple[tuple[str, str, str], ...] = (
    ('users', 'SELECT', f'id = {_UID}'),
    ('users', 'UPDATE', f'id = {_UID}'),
    ('workflows', 'SELECT', f'user_id = {_UID}'),
    ('workflows', 'INSERT', f'user_id = {_UID}'),
    ('workflows', 'UPDATE', f'user_id = {_UID}'),
    ('workflows', 'DELETE', f'user_id = {_UID}'),
    ('agent_nodes', 'SELECT', _OWNS_WORKFLOW.format(col='agent_nodes.workflow_id')),
    ('agent_nodes', 'INSERT', _OWNS_WORKFLOW.format(col='agent_nodes.workflow_id')),
    ('agent_nodes', 'UPDATE', _OWNS_WORKFLOW.format(col='agent_nodes.workflow_id')),
    ('agent_nodes', 'DELETE', _OWNS_WORKFLOW.format(col='agent_nodes.workflow_id')),
    ('execution_runs', 'SELECT', _OWNS_WORKFLOW.format(col='execution_runs.workflow_id')),
    ('execution_logs', 'SELECT', _OWNS_WORKFLOW.format(col='execution_logs.workflow_id')),
    ('agent_outputs', 'SELECT', _OWNS_LOG.format(col='agent_outputs.log_id')),
    ('approvals', 'SELECT', _OWNS_LOG.format(col='approvals.log_id')),
)


def _policy_name(table: str, command: str) -> str:
    return f'{table}_{command.lower()}_own'


def _create_policy(table: str, command: str, predicate: str) -> str:
    name = _policy_name(table, command)
    if command == 'INSERT':
        clause = f'WITH CHECK ({predicate})'
    elif command == 'UPDATE':
        clause = f'USING ({predicate}) WITH CHECK ({predicate})'
    else:
        clause = f'USING ({predicate})'
    return f'CREATE POLICY {name} ON public.{table} AS PERMISSIVE FOR {command} TO authenticated {clause};'


def upgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')

    policies = '\n        '.join(_create_policy(*p) for p in POLICIES)
    op.execute(
        f"""
        DO $rls$
        BEGIN
          IF {_SUPABASE} THEN
            {policies}
          END IF;
        END
        $rls$;
        """
    )

    op.execute(
        """
        DO $revoke$
        BEGIN
          IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
            REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
              REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
              REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM authenticated;
            END IF;
          END IF;
        END
        $revoke$;
        """
    )


def downgrade() -> None:
    for table, command, _ in POLICIES:
        op.execute(f'DROP POLICY IF EXISTS {_policy_name(table, command)} ON public.{table}')

    # Plain Postgres only — see the module docstring for why Supabase keeps RLS on.
    disable = '\n          '.join(f'ALTER TABLE public.{t} DISABLE ROW LEVEL SECURITY;' for t in RLS_TABLES)
    op.execute(
        f"""
        DO $rls$
        BEGIN
          IF to_regprocedure('auth.uid()') IS NULL THEN
          {disable}
          END IF;
        END
        $rls$;
        """
    )
