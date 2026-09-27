"""Row Level Security (migration 0002) against a real PostgreSQL.

These tests OWN the database they are pointed at: they downgrade it to base and upgrade it
again. They run only when `RLS_TEST_DATABASE_URL` is set, and skip otherwise — never point it
at a database whose data you want to keep. CI sets it in the `db-migrations` job.

    RLS_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/rls_test pytest db/tests/test_rls.py

The second test makes the database look like Supabase (an `auth.uid()` that reads the JWT
`sub` claim, and `anon`/`authenticated` roles) so the policies are created and exercised:
each user sees only their own rows, and nobody sees `credentials`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

URL = os.environ.get("RLS_TEST_DATABASE_URL")
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
APP_TABLES = {
    "users",
    "workflows",
    "agent_nodes",
    "execution_runs",
    "execution_logs",
    "agent_outputs",
    "credentials",
    "approvals",
}
RLS_TABLES = APP_TABLES | {"alembic_version"}


@pytest.fixture(scope="module")
def url() -> str:
    if not URL:
        pytest.skip("RLS_TEST_DATABASE_URL is not set")
    try:
        psycopg.connect(URL, connect_timeout=3).close()
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    return URL


@pytest.fixture()
def alembic_cfg(url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("DATABASE_URL", url)  # migrations/env.py reads it
    return Config(str(ALEMBIC_INI))


@pytest.fixture()
def conn(url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(url, autocommit=True) as c:
        yield c


def rls_enabled(conn: psycopg.Connection) -> dict[str, bool]:
    rows = conn.execute(
        "SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
    ).fetchall()
    return {name: on for name, on in rows if name in RLS_TABLES}


def policy_count(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'").fetchone()[0]


def test_plain_postgres_enables_rls_everywhere_without_policies(alembic_cfg: Config, conn: psycopg.Connection):
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    assert rls_enabled(conn) == dict.fromkeys(RLS_TABLES, True)
    assert policy_count(conn) == 0  # no auth schema here, so the policy block is a no-op

    # The table owner (how the API and worker connect) is unaffected by RLS.
    conn.execute("INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'owner@x.co')")
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1

    command.downgrade(alembic_cfg, "0001")
    assert rls_enabled(conn) == dict.fromkeys(RLS_TABLES, False)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture()
def supabase_like(alembic_cfg: Config, conn: psycopg.Connection) -> Iterator[None]:
    """Fake just enough of Supabase: auth.uid(), anon/authenticated, rls_auto_enable()."""
    created_roles = []
    command.downgrade(alembic_cfg, "0001")
    for role in ("anon", "authenticated"):
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            conn.execute(f"CREATE ROLE {role} NOLOGIN")
            created_roles.append(role)
    conn.execute("CREATE SCHEMA IF NOT EXISTS auth")
    conn.execute(
        "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$"
    )
    conn.execute(
        "CREATE OR REPLACE FUNCTION public.rls_auto_enable() RETURNS void LANGUAGE sql SECURITY DEFINER AS $$ SELECT $$"
    )
    conn.execute("GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO anon, authenticated")
    # PostgREST's default grants: the API roles may touch every table; RLS decides which rows.
    conn.execute("GRANT USAGE ON SCHEMA public, auth TO anon, authenticated")
    conn.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon, authenticated")
    conn.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated"
    )
    command.upgrade(alembic_cfg, "head")
    try:
        yield
    finally:
        command.downgrade(alembic_cfg, "base")
        conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated")
        conn.execute("DROP FUNCTION IF EXISTS public.rls_auto_enable()")
        conn.execute("DROP SCHEMA auth CASCADE")
        conn.execute("REVOKE ALL ON SCHEMA public FROM anon, authenticated")
        for role in created_roles:
            conn.execute(f"DROP OWNED BY {role}")
            conn.execute(f"DROP ROLE {role}")
        command.upgrade(alembic_cfg, "head")


def _seed_user(conn: psycopg.Connection, email: str) -> uuid.UUID:
    uid, wf, run, log = (uuid.uuid4() for _ in range(4))
    conn.execute("INSERT INTO users (id, email) VALUES (%s, %s)", (uid, email))
    conn.execute("INSERT INTO workflows (id, user_id, name, graph_definition) VALUES (%s, %s, 'w', '{}')", (wf, uid))
    conn.execute(
        "INSERT INTO agent_nodes (id, workflow_id, agent_type, configuration, position_order) "
        "VALUES (gen_random_uuid(), %s, 'writer', '{}', 0)",
        (wf,),
    )
    conn.execute(
        "INSERT INTO execution_runs (id, workflow_id, triggered_by, graph_snapshot) VALUES (%s, %s, %s, '{}')",
        (run, wf, uid),
    )
    conn.execute(
        "INSERT INTO execution_logs (id, run_id, workflow_id, node_id, agent_type) "
        "VALUES (%s, %s, %s, gen_random_uuid(), 'writer')",
        (log, run, wf),
    )
    conn.execute(
        "INSERT INTO agent_outputs (id, log_id, output_type, content) VALUES (gen_random_uuid(), %s, 'text', 'x')",
        (log,),
    )
    conn.execute(
        "INSERT INTO approvals (id, log_id, decision, decided_by) VALUES (gen_random_uuid(), %s, 'approve', %s)",
        (log, uid),
    )
    conn.execute(
        "INSERT INTO credentials (id, user_id, provider, encrypted_payload) VALUES (gen_random_uuid(), %s, 'google', 'x')",
        (uid,),
    )
    return uid


def _visible(conn: psycopg.Connection, role: str, sub: uuid.UUID | None) -> dict[str, int]:
    with conn.transaction(force_rollback=True):
        conn.execute(f"SET LOCAL ROLE {role}")
        conn.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (str(sub) if sub else "",))
        return {t: conn.execute(f"SELECT count(*) FROM public.{t}").fetchone()[0] for t in APP_TABLES}


def test_supabase_policies_isolate_users(supabase_like: None, conn: psycopg.Connection):
    assert rls_enabled(conn) == dict.fromkeys(RLS_TABLES, True)
    assert conn.execute("SELECT count(*) FROM pg_policies WHERE 'anon' = ANY(roles)").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM pg_policies WHERE tablename = 'credentials'").fetchone()[0] == 0

    alice = _seed_user(conn, "alice@x.co")
    bob = _seed_user(conn, "bob@x.co")

    own_rows = dict.fromkeys(APP_TABLES, 1) | {"credentials": 0}
    assert _visible(conn, "authenticated", alice) == own_rows
    assert _visible(conn, "authenticated", bob) == own_rows
    assert _visible(conn, "authenticated", None) == dict.fromkeys(APP_TABLES, 0)
    assert _visible(conn, "anon", None) == dict.fromkeys(APP_TABLES, 0)

    # Alice cannot create a workflow for Bob, nor rename Bob's.
    with conn.transaction(force_rollback=True):
        conn.execute("SET LOCAL ROLE authenticated")
        conn.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (str(alice),))
        assert conn.execute("UPDATE workflows SET name = 'hacked' WHERE user_id = %s", (bob,)).rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO workflows (id, user_id, name, graph_definition) VALUES (gen_random_uuid(), %s, 'x', '{}')",
                (bob,),
            )

    # The advisor-flagged SECURITY DEFINER function is no longer callable by the API roles.
    for role in ("anon", "authenticated"):
        assert not conn.execute(
            "SELECT has_function_privilege(%s, 'public.rls_auto_enable()', 'EXECUTE')", (role,)
        ).fetchone()[0]

    # On Supabase, downgrading keeps RLS on (turning it off would expose tables to the anon key).
    cfg = Config(str(ALEMBIC_INI))
    command.downgrade(cfg, "0001")
    assert policy_count(conn) == 0
    assert rls_enabled(conn) == dict.fromkeys(RLS_TABLES, True)
