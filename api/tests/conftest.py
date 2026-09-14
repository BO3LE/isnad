"""API tests run with no worker, no Redis and no PostgreSQL: SQLite in memory plus fakes."""

from __future__ import annotations

import itertools
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.auth import issue_token
from api.catalog import StaticCatalog
from api.deps import get_catalog, get_enqueuer, get_session
from api.main import create_app
from api.settings import ApiSettings, get_settings
from contracts.manifest import AgentManifest
from db.models import Base, User

SETTINGS = ApiSettings(
    environment="test", jwt_secret="test-secret-that-is-long-enough-for-hs256", storage_root="/nonexistent"
)

CATALOG = [
    AgentManifest(
        name="researcher",
        version="0.1.0",
        title="Researcher",
        description="d",
        input_type="ResearchInput",
        output_type="ResearchOutput",
        config_schema={"properties": {"topic": {"title": "Topic"}}, "required": ["topic"]},
    ),
    AgentManifest(
        name="writer",
        version="0.1.0",
        title="Writer",
        description="d",
        input_type="WriteInput",
        output_type="WriteOutput",
        config_schema={"properties": {}},
    ),
]


class RecordingEnqueuer:
    def __init__(self) -> None:
        self.runs: list[UUID] = []

    def enqueue_run(self, run_id: UUID) -> None:
        self.runs.append(run_id)


@pytest.fixture()
def sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def enqueuer() -> RecordingEnqueuer:
    return RecordingEnqueuer()


@pytest.fixture()
def catalog() -> StaticCatalog:
    return StaticCatalog(CATALOG)


@pytest.fixture()
def client(sessions, enqueuer, catalog):
    app = create_app(SETTINGS)

    def session_override():
        with sessions() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_enqueuer] = lambda: enqueuer
    app.dependency_overrides[get_catalog] = lambda: catalog
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(sessions, email: str = "hasan@gp.local") -> dict[str, str]:
    with sessions() as s:
        user = User(id=uuid4(), email=email)
        s.add(user)
        s.commit()
        return {"Authorization": f"Bearer {issue_token(SETTINGS, user.id, user.email)}"}


@pytest.fixture()
def headers(sessions) -> dict[str, str]:
    return auth_headers(sessions)


def graph(*agent_types: str, configs: list[dict] | None = None, connect: bool = True) -> dict:
    nodes = [
        {
            "id": str(uuid4()),
            "agent_type": t,
            "configuration": (configs or [{}] * len(agent_types))[i],
            "position": {"x": i * 300, "y": 0},
        }
        for i, t in enumerate(agent_types)
    ]
    edges = (
        [{"id": f"e{i}", "source": a["id"], "target": b["id"]} for i, (a, b) in enumerate(itertools.pairwise(nodes))]
        if connect
        else []
    )
    return {"nodes": nodes, "edges": edges}
