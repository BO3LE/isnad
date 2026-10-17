"""Schema tests that need no running database (SQLite in memory).

The full migration round-trip against PostgreSQL runs in CI (`db-migrations` job):
`alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic check`.
"""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import Base, Credential, ExecutionLog, ExecutionRun, User, Workflow


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_eight_tables():
    assert set(Base.metadata.tables) == {
        "users",
        "workflows",
        "agent_nodes",
        "execution_runs",
        "execution_logs",
        "agent_outputs",
        "credentials",
        "approvals",
    }


def test_retry_count_is_capped_at_three(session):
    user = User(email="a@b.co")
    session.add(user)
    session.flush()
    wf = Workflow(user_id=user.id, name="w", graph_definition={})
    session.add(wf)
    session.flush()
    run = ExecutionRun(workflow_id=wf.id, graph_snapshot={})
    session.add(run)
    session.flush()
    session.add(
        ExecutionLog(run_id=run.id, workflow_id=wf.id, node_id=uuid.uuid4(), agent_type="writer", retry_count=4)
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_seed_templates_are_valid_chains():
    from db.seed import TEMPLATES

    for _, graph in TEMPLATES:
        ids = [n["id"] for n in graph["nodes"]]
        assert len(ids) == len(set(ids))
        assert len(graph["edges"]) == len(ids) - 1


def test_session_round_trip(session):
    session.add(User(email="x@y.co"))
    session.commit()
    assert session.scalar(select(User.email)) == "x@y.co"


def test_an_account_has_one_connection_per_access(session):
    """Google grants YouTube apart from Drive and Gmail, so one account can have a row for each."""
    user = User(email="a@b.co")
    session.add(user)
    session.flush()
    for access in ("youtube", "drive_gmail"):
        session.add(
            Credential(
                user_id=user.id, provider="google", account_email="a@gmail.com", access=access, encrypted_payload=b"x"
            )
        )
    session.flush()
    session.add(
        Credential(
            user_id=user.id, provider="google", account_email="a@gmail.com", access="youtube", encrypted_payload=b"x"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
