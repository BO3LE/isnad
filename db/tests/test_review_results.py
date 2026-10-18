"""Migration 0007 (a step's result reviewed, redone and decided again) against a real PostgreSQL.

Owns the database it is pointed at: it downgrades to 0006 and upgrades to head. Runs only when
`RLS_TEST_DATABASE_URL` is set (CI sets it in the `db-migrations` job) and skips otherwise — never
point it at a database whose data you want to keep.

    RLS_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/rls_test pytest db/tests/test_review_results.py
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


def a_step(conn: psycopg.Connection) -> uuid.UUID:
    """A user, a workflow, a run and one step of it: what a decision hangs on."""
    user_id, workflow_id, run_id, log_id = (uuid.uuid4() for _ in range(4))
    conn.execute("INSERT INTO users (id, email) VALUES (%s, %s)", (user_id, f"{user_id}@gp.local"))
    conn.execute(
        "INSERT INTO workflows (id, user_id, name, graph_definition) VALUES (%s, %s, 'w', '{}')",
        (workflow_id, user_id),
    )
    conn.execute(
        "INSERT INTO execution_runs (id, workflow_id, graph_snapshot) VALUES (%s, %s, '{}')", (run_id, workflow_id)
    )
    conn.execute(
        "INSERT INTO execution_logs (id, run_id, workflow_id, node_id, agent_type) VALUES (%s, %s, %s, %s, 'writer')",
        (log_id, run_id, workflow_id, uuid.uuid4()),
    )
    return log_id


def decide(conn: psycopg.Connection, log_id: uuid.UUID, decision: str, revision: int | None = None) -> None:
    if revision is None:
        conn.execute(
            "INSERT INTO approvals (id, log_id, decision) VALUES (%s, %s, %s)", (uuid.uuid4(), log_id, decision)
        )
    else:
        conn.execute(
            "INSERT INTO approvals (id, log_id, decision, revision) VALUES (%s, %s, %s, %s)",
            (uuid.uuid4(), log_id, decision, revision),
        )


def test_a_result_is_decided_once_per_revision_and_downgrade_will_not_drop_decisions(alembic_cfg, conn):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "0006")
    conn.execute("DELETE FROM users")
    decided_before = a_step(conn)
    decide(conn, decided_before, "approve")

    command.upgrade(alembic_cfg, "head")
    assert conn.execute("SELECT revision, edited FROM approvals").fetchall() == [(0, False)]
    assert conn.execute("SELECT revision FROM execution_logs").fetchall() == [(0,)]

    step = a_step(conn)
    decide(conn, step, "redo", revision=0)
    decide(conn, step, "approve", revision=1)  # the redone result, decided in its turn
    with pytest.raises(psycopg.errors.UniqueViolation):
        decide(conn, step, "reject", revision=1)  # a second decision on the same result

    # One decision per step again would have to delete some; it refuses instead.
    with pytest.raises(RuntimeError, match="decided more than once"):
        command.downgrade(alembic_cfg, "0006")
    conn.execute("DELETE FROM approvals WHERE log_id = %s", (step,))
    command.downgrade(alembic_cfg, "0006")
    assert conn.execute("SELECT decision FROM approvals").fetchall() == [("approve",)]
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        decide(conn, step, "redo")  # 0006 has no such decision
    command.upgrade(alembic_cfg, "head")
    conn.execute("DELETE FROM users")
