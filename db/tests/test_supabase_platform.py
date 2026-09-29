"""Supabase platform setup (migration 0005) against a real PostgreSQL.

Owns the database it is pointed at: it downgrades to 0004 and upgrades to head repeatedly. Runs
only when `RLS_TEST_DATABASE_URL` is set (the same database test_rls.py uses — CI sets it in the
`db-migrations` job) and skips otherwise — never point it at a database whose data you want to
keep.

    RLS_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/rls_test pytest db/tests/test_supabase_platform.py

Fakes just enough of Supabase's platform surface — a `supabase_realtime` publication and a
minimal `storage.buckets` table — to exercise the guarded upgrade/downgrade without touching the
real Supabase project. See db/migrations/versions/0005_supabase_platform.py and
db/tests/test_rls.py (the same simulated-Supabase approach, for RLS).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

URL = os.environ.get("RLS_TEST_DATABASE_URL")
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
REALTIME_TABLES = {"execution_runs", "execution_logs"}


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


def publication_tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT tablename FROM pg_publication_tables WHERE pubname = 'supabase_realtime' AND schemaname = 'public'"
    ).fetchall()
    return {r[0] for r in rows}


def bucket_row(conn: psycopg.Connection) -> tuple[str, bool] | None:
    return conn.execute("SELECT id, public FROM storage.buckets WHERE id = 'artifacts'").fetchone()


def test_plain_postgres_is_a_no_op(alembic_cfg: Config, conn: psycopg.Connection):
    """No `supabase_realtime` publication and no `storage` schema here, so 0005 does nothing."""
    command.downgrade(alembic_cfg, "0004")
    command.upgrade(alembic_cfg, "head")

    assert conn.execute("SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'").fetchone() is None
    assert conn.execute("SELECT to_regclass('storage.buckets')").fetchone()[0] is None


@pytest.fixture()
def fake_supabase_platform(alembic_cfg: Config, conn: psycopg.Connection) -> Iterator[None]:
    """Fake just enough of Supabase's platform surface: a Realtime publication and storage.buckets."""
    command.downgrade(alembic_cfg, "0004")
    conn.execute("CREATE PUBLICATION supabase_realtime")
    conn.execute("CREATE SCHEMA IF NOT EXISTS storage")
    conn.execute(
        """
        CREATE TABLE storage.buckets (
            id text PRIMARY KEY,
            name text NOT NULL,
            public boolean NOT NULL DEFAULT false
        )
        """
    )
    try:
        yield
    finally:
        command.downgrade(alembic_cfg, "0004")
        conn.execute("DROP TABLE IF EXISTS storage.buckets")
        conn.execute("DROP SCHEMA IF EXISTS storage")
        conn.execute("DROP PUBLICATION IF EXISTS supabase_realtime")
        command.upgrade(alembic_cfg, "head")


def test_supabase_platform_upgrade_and_downgrade(fake_supabase_platform: None, conn: psycopg.Connection):
    cfg = Config(str(ALEMBIC_INI))

    # Simulate the publication already containing one of the two tables (e.g. a previous
    # partial run, or something added by hand) — the upgrade must skip it, not error.
    conn.execute("ALTER PUBLICATION supabase_realtime ADD TABLE public.execution_runs")

    command.upgrade(cfg, "head")

    assert publication_tables(conn) == REALTIME_TABLES
    row = bucket_row(conn)
    assert row is not None
    assert row == ("artifacts", False)  # private

    # Idempotent: an existing bucket (e.g. the hand-made one from before this migration existed)
    # is forced private again, not duplicated or left alone.
    conn.execute("UPDATE storage.buckets SET public = true WHERE id = 'artifacts'")
    command.downgrade(cfg, "0004")
    command.upgrade(cfg, "head")
    assert publication_tables(conn) == REALTIME_TABLES
    assert bucket_row(conn) == ("artifacts", False)

    # Downgrade removes the two tables from the publication but does NOT delete the bucket.
    command.downgrade(cfg, "0004")
    assert publication_tables(conn) == set()
    assert bucket_row(conn) == ("artifacts", False)

    command.upgrade(cfg, "head")
