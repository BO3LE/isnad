"""With STORAGE_BACKEND=supabase a run's files are uploaded to the bucket under {user}/{run}/.

The Supabase Storage REST API is replaced by an httpx MockTransport — no network.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
from conftest import TextIn, _manifest, chain
from pydantic import BaseModel

from adapters.factory import AdapterSettings, build_ports
from adapters.storage.supabase import SupabaseStorage
from contracts.agent import BaseAgent
from contracts.run import RunStatus
from worker.orchestrator import Orchestrator
from worker.registry import Registry
from worker.settings import WorkerSettings, adapter_settings

URL = "https://example.supabase.co"


class FileOut(BaseModel):
    file_path: str


class ConfigIn(BaseModel):
    text: str = "hello"


class FileAgent(BaseAgent[TextIn, FileOut]):
    manifest = _manifest("filer")
    input_model, output_model, config_model = TextIn, FileOut, ConfigIn

    async def execute(self, input_data, ports):
        path = await ports.storage.put("artifacts/notes/n1/note.txt", input_data.text.encode(), "text/plain")
        return FileOut(file_path=path)


async def test_a_runs_file_is_uploaded_to_the_bucket_and_its_bucket_path_saved(store):
    uploads = []

    def handler(request: httpx.Request) -> httpx.Response:
        uploads.append((request.method, str(request.url), request.content, request.headers["authorization"]))
        return httpx.Response(200, json={"Key": "artifacts/..."})

    ports = build_ports(
        AdapterSettings(fake=True, storage_backend="supabase", supabase_url=URL, supabase_service_key="service-key")
    )
    assert isinstance(ports.storage, SupabaseStorage)
    ports.storage._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))

    graph = chain("filer", config={"text": "hello"})
    run_id, user_id = uuid4(), uuid4()
    store.create_run(run_id, graph, user_id=user_id)

    status = await Orchestrator(store, Registry([FileAgent]), ports).execute(run_id)

    assert status == RunStatus.SUCCEEDED
    bucket_path = f"{user_id}/{run_id}/notes/n1/note.txt"
    assert store.outputs[(run_id, graph.nodes[0].id)]["file_path"] == bucket_path
    assert uploads == [("POST", f"{URL}/storage/v1/object/artifacts/{bucket_path}", b"hello", "Bearer service-key")]


def test_worker_settings_select_the_storage_backend(tmp_path):
    local = adapter_settings(WorkerSettings(_env_file=None, storage_root=str(tmp_path)))
    assert local.storage_backend == "local"
    assert local.storage_root == str(tmp_path)

    remote = adapter_settings(
        WorkerSettings(
            _env_file=None,
            storage_backend="supabase",
            supabase_url=URL,
            supabase_service_key="service-key",
            storage_bucket="artifacts",
        )
    )
    assert (remote.storage_backend, remote.supabase_url, remote.storage_bucket) == ("supabase", URL, "artifacts")
    assert isinstance(build_ports(remote).storage, SupabaseStorage)
