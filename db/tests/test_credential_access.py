"""Migration 0006 (a Google account connected once per access) against a real PostgreSQL.

Owns the database it is pointed at: it downgrades to 0005 and upgrades to head. Runs only when
`RLS_TEST_DATABASE_URL` is set (CI sets it in the `db-migrations` job) and skips otherwise — never
point it at a database whose data you want to keep.

    RLS_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/rls_test pytest db/tests/test_credential_access.py
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


def add_credential(conn: psycopg.Connection, user_id: uuid.UUID, access: str | None = None) -> None:
    columns = "id, user_id, provider, account_email, scopes, encrypted_payload" + (", access" if access else "")
    values = "%s, %s, 'google', 'team@example.org', '[]', 'x'" + (", %s" if access else "")
    params = [uuid.uuid4(), user_id, *([access] if access else [])]
    conn.execute(f"INSERT INTO credentials ({columns}) VALUES ({values})", params)


def test_an_account_gets_one_connection_per_access_and_downgrade_will_not_pick_one(alembic_cfg, conn):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "0005")
    conn.execute("DELETE FROM credentials")
    user_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, f"{user_id}@gp.local")
    )
    add_credential(conn, user_id)  # connected before the split

    command.upgrade(alembic_cfg, "head")
    assert conn.execute("SELECT access FROM credentials").fetchall() == [("all",)]

    add_credential(conn, user_id, "youtube")
    add_credential(conn, user_id, "drive_gmail")
    with pytest.raises(psycopg.errors.UniqueViolation):
        add_credential(conn, user_id, "youtube")  # reconnecting updates that row instead

    # Back to one row per account would have to delete connections; it refuses instead.
    with pytest.raises(RuntimeError, match="more than one connection"):
        command.downgrade(alembic_cfg, "0005")
    conn.execute("DELETE FROM credentials WHERE access <> 'all'")
    command.downgrade(alembic_cfg, "0005")
    command.upgrade(alembic_cfg, "head")
    conn.execute("DELETE FROM credentials")
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
