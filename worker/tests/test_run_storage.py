"""Every file a run writes lands under `{user_id}/{run_id}/` (GP-plan W4 — `artifacts/{user}/{run}/`)."""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from conftest import TextIn, TextOut, _manifest, chain
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adapters.publish.fake import FakePublisher
from adapters.storage.local import LocalStorage
from contracts.agent import BaseAgent
from contracts.errors import NonRetryableAgentError
from contracts.ports import PublishMetadata
from contracts.run import RunStatus
from db.models import Base, ExecutionRun, User, Workflow
from worker.orchestrator import Orchestrator
from worker.registry import Registry
from worker.run_storage import RunScopedStorage, run_ports
from worker.store import SqlRunStore

USER, RUN = uuid4(), uuid4()


@pytest.fixture()
def scoped(tmp_path) -> RunScopedStorage:
    return RunScopedStorage(LocalStorage(tmp_path), USER, RUN)


# --- the wrapper ---------------------------------------------------------------------


async def test_a_write_lands_in_the_runs_folder(scoped, tmp_path):
    path = await scoped.put("artifacts/videos/ab12/video.mp4", b"mp4", "video/mp4")

    assert path == f"{USER}/{RUN}/videos/ab12/video.mp4"
    assert (tmp_path / str(USER) / str(RUN) / "videos" / "ab12" / "video.mp4").read_bytes() == b"mp4"


async def test_a_path_without_the_artifacts_root_is_prefixed_too(scoped):
    assert await scoped.put("report.pdf", b"%PDF", "application/pdf") == f"{USER}/{RUN}/report.pdf"


async def test_scoping_is_idempotent(scoped):
    once = scoped.scoped("artifacts/images/x/image-1.png")
    assert scoped.scoped(once) == once


async def test_the_returned_path_reads_back_and_signs(scoped):
    path = await scoped.put("artifacts/images/x/image-1.png", b"png", "image/png")

    assert await scoped.get(path) == b"png"
    assert (await scoped.signed_url(path)).endswith(f"/files/{USER}/{RUN}/images/x/image-1.png")


@pytest.mark.parametrize("bad", ["/etc/passwd", "../escape.txt", "artifacts/../../escape.txt", ""])
def test_an_escaping_path_is_refused(scoped, bad):
    with pytest.raises(ValueError):
        scoped.scoped(bad)


async def test_another_users_file_is_refused(scoped, tmp_path):
    other = f"{uuid4()}/{uuid4()}/videos/v/video.mp4"
    with pytest.raises(NonRetryableAgentError):
        await scoped.get(other)
    with pytest.raises(NonRetryableAgentError):
        await scoped.signed_url(other)


async def test_a_file_from_before_per_run_folders_is_still_readable(scoped, tmp_path):
    legacy = tmp_path / "artifacts" / "videos" / "old"
    legacy.mkdir(parents=True)
    (legacy / "video.mp4").write_bytes(b"old")

    assert await scoped.get("artifacts/videos/old/video.mp4") == b"old"


async def test_a_run_with_no_known_owner_is_still_kept_apart(tmp_path):
    storage = RunScopedStorage(LocalStorage(tmp_path), None, RUN)
    assert await storage.put("artifacts/a.txt", b"a", "text/plain") == f"{RUN}/a.txt"


async def test_run_ports_scope_storage_and_guard_publishers(ports):
    publisher = FakePublisher("drive")
    scoped_ports = run_ports(dataclasses.replace(ports, publishers={"drive": publisher}), USER, RUN)
    assert isinstance(scoped_ports.storage, RunScopedStorage)
    assert scoped_ports.llm is ports.llm

    await scoped_ports.publishers["drive"].publish(f"{USER}/{RUN}/v.mp4", PublishMetadata(title="t"))
    assert publisher.published[0][0] == f"{USER}/{RUN}/v.mp4"
    with pytest.raises(NonRetryableAgentError):
        await scoped_ports.publishers["drive"].publish(f"{uuid4()}/{RUN}/v.mp4", PublishMetadata(title="t"))


# --- through the orchestrator ------------------------------------------------------


class FileOut(BaseModel):
    file_path: str


class FileAgent(BaseAgent[TextIn, FileOut]):
    """Writes the path an agent always has — the worker decides the folder."""

    manifest = _manifest("filer")
    input_model, output_model, config_model = TextIn, FileOut, TextOut

    async def execute(self, input_data, ports):
        path = await ports.storage.put("artifacts/notes/n1/note.txt", input_data.text.encode(), "text/plain")
        return FileOut(file_path=path)


async def test_a_runs_files_are_saved_under_its_owner_and_run(store, ports, tmp_path):
    graph = chain("filer", config={"text": "hello"})
    run_id, user_id = uuid4(), uuid4()
    store.create_run(run_id, graph, user_id=user_id)

    status = await Orchestrator(store, Registry([FileAgent]), ports).execute(run_id)

    assert status == RunStatus.SUCCEEDED
    saved = store.outputs[(run_id, graph.nodes[0].id)]["file_path"]
    assert saved == f"{user_id}/{run_id}/notes/n1/note.txt"
    assert (tmp_path / saved).read_bytes() == b"hello"


async def test_two_runs_of_the_same_graph_do_not_share_a_folder(store, ports):
    graph = chain("filer", config={"text": "hello"})
    user_id = uuid4()
    paths = []
    for _ in range(2):
        run_id = uuid4()
        store.create_run(run_id, graph, user_id=user_id)
        await Orchestrator(store, Registry([FileAgent]), ports).execute(run_id)
        paths.append(store.outputs[(run_id, graph.nodes[0].id)]["file_path"])
    assert paths[0] != paths[1]


# --- the production store knows the owner ------------------------------------------


def test_sql_store_loads_the_workflows_owner():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    user, workflow, run = User(email="a@example.com"), None, None
    with sessions.begin() as s:
        s.add(user)
        s.flush()
        workflow = Workflow(user_id=user.id, name="w")
        s.add(workflow)
        s.flush()
        run = ExecutionRun(workflow_id=workflow.id, graph_snapshot=chain("filer").model_dump(mode="json"))
        s.add(run)

    snap = SqlRunStore(sessions).load(run.id)

    assert snap.user_id == user.id
