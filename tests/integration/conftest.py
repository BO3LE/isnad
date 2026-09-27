"""Integration fixtures: a real PostgreSQL, the real `SqlRunStore`, the installed agents, fake adapters.

These tests cross component boundaries on purpose, so they live outside every component and are
not part of `scripts/test_all.sh`. They need a PostgreSQL they may migrate and write to:

    INTEGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/c7_integration \
        python -m pytest tests/integration

`INTEGRATION_DATABASE_URL` wins over `DATABASE_URL`. With neither set, or the server unreachable,
every test here is skipped — unless `REQUIRE_INTEGRATION_DB=1` (CI sets it), when that is a failure.
The video-template test likewise needs FFmpeg on PATH.
The database is migrated to head and seeded on first use; both steps are idempotent. Every run and
workflow a test creates is deleted afterwards, so a dev database is left as it was found.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from adapters.factory import AdapterSettings, build_ports
from contracts.graph import topological_order
from contracts.ports import Ports
from contracts.run import NodeStatus, RunStatus, WorkflowGraph
from db.models import ExecutionLog, ExecutionRun, User, Workflow
from db.seed import DEMO_EMAIL, seed
from db.session import make_engine, make_session_factory
from worker.registry import Registry
from worker.store import SqlRunStore

REPO = Path(__file__).resolve().parents[2]
REQUIRED_AGENTS = {"researcher", "writer", "email", "video", "publisher"}


def unavailable(reason: str) -> None:
    if os.environ.get("REQUIRE_INTEGRATION_DB") == "1":
        pytest.fail(f"REQUIRE_INTEGRATION_DB=1 but {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def ffmpeg() -> None:
    """The video agent renders with FFmpeg; without it the video template cannot run."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        unavailable("FFmpeg is not installed — the video template needs it")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("INTEGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        unavailable("no INTEGRATION_DATABASE_URL / DATABASE_URL — integration tests need PostgreSQL")
    engine = make_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:
        unavailable(f"PostgreSQL is not reachable at the configured URL ({exc.__class__.__name__})")
    finally:
        engine.dispose()
    return url


@pytest.fixture(scope="session")
def session_factory(database_url: str) -> Iterator[sessionmaker[Session]]:
    from alembic import command
    from alembic.config import Config

    # migrations/env.py reads DATABASE_URL itself.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(str(REPO / "db" / "alembic.ini")), "head")
    finally:
        if previous is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = previous
    seed(database_url)

    engine = make_engine(database_url)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def registry() -> Registry:
    """The agents discovered exactly as the worker discovers them: by `gp.agents` entry point."""
    found = Registry.from_entry_points()
    missing = REQUIRED_AGENTS - {m.name for m in found.catalog()}
    assert not missing, f"install the agents first (pip install ./agents/...): missing {sorted(missing)}"
    return found


@pytest.fixture()
def storage_root(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ports(storage_root: Path) -> Ports:
    return build_ports(AdapterSettings(fake=True, storage_root=str(storage_root)))


class RecordingStore(SqlRunStore):
    """The production store, plus a log of every status it wrote — in the order it wrote them."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.history: list[tuple[str, uuid.UUID | None, str]] = []

    def set_run_status(self, run_id, status):
        self.history.append(("run", None, RunStatus(status).value))
        super().set_run_status(run_id, status)

    def set_node_status(self, run_id, node_id, status, *, retry_count=None, error=None):
        self.history.append(("node", node_id, NodeStatus(status).value))
        super().set_node_status(run_id, node_id, status, retry_count=retry_count, error=error)

    def run_transitions(self) -> list[str]:
        return [status for kind, _, status in self.history if kind == "run"]

    def node_transitions(self, node_id: uuid.UUID) -> list[str]:
        return [status for kind, nid, status in self.history if kind == "node" and nid == node_id]


@pytest.fixture()
def store(session_factory: sessionmaker[Session], storage_root: Path) -> RecordingStore:
    return RecordingStore(session_factory, str(storage_root))


class Db:
    """What the API does to the database around a run, done directly (no HTTP, no queue)."""

    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions
        self._runs: list[uuid.UUID] = []
        self._workflows: list[uuid.UUID] = []

    def demo_user_id(self) -> uuid.UUID:
        with self.sessions() as s:
            return s.scalar(select(User.id).where(User.email == DEMO_EMAIL))

    def template(self, name: str) -> Workflow:
        with self.sessions() as s:
            workflow = s.scalar(select(Workflow).where(Workflow.user_id == self.demo_user_id(), Workflow.name == name))
            assert workflow is not None, f"seeded template {name!r} not found"
            return workflow

    def create_workflow(self, name: str, graph: WorkflowGraph) -> uuid.UUID:
        with self.sessions.begin() as s:
            workflow = Workflow(user_id=self.demo_user_id(), name=name, graph_definition=graph.model_dump(mode="json"))
            s.add(workflow)
            s.flush()
            self._workflows.append(workflow.id)
            return workflow.id

    def start_run(self, workflow_id: uuid.UUID) -> uuid.UUID:
        """Mirror of `POST /workflows/{id}/run` (api/routers/workflows.py) up to the enqueue."""
        with self.sessions.begin() as s:
            workflow = s.get(Workflow, workflow_id)
            graph = WorkflowGraph.model_validate(workflow.graph_definition or {})
            run = ExecutionRun(
                workflow_id=workflow.id,
                triggered_by=workflow.user_id,
                status=RunStatus.QUEUED.value,
                graph_snapshot=graph.model_dump(mode="json"),
                total_nodes=len(graph.nodes),
            )
            s.add(run)
            s.flush()
            for order, node in enumerate(topological_order(graph)):
                s.add(
                    ExecutionLog(
                        run_id=run.id,
                        workflow_id=workflow.id,
                        node_id=node.id,
                        agent_type=node.agent_type,
                        position_order=order,
                        status=NodeStatus.PENDING.value,
                    )
                )
            self._runs.append(run.id)
            return run.id

    def cleanup(self) -> None:
        with self.sessions.begin() as s:
            if self._runs:
                s.execute(delete(ExecutionRun).where(ExecutionRun.id.in_(self._runs)))
            if self._workflows:
                s.execute(delete(Workflow).where(Workflow.id.in_(self._workflows)))


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Db]:
    helper = Db(session_factory)
    yield helper
    helper.cleanup()


class Sleeps(list):
    """Records backoff delays instead of waiting them out."""

    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture()
def sleeps() -> Sleeps:
    return Sleeps()
