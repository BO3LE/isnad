"""The "Blog post" template with the Writer on a local model — LLM_PROVIDER=local, as with LM Studio.

Everything is real except the model: the orchestrator, SqlRunStore on PostgreSQL, the installed
agents, and `OpenAICompatibleLLM` with the `openai` SDK, talking HTTP over a real socket to a
stand-in that speaks LM Studio's OpenAI-compatible API (streaming included). So this proves the
wiring and the failure handling. It does not prove that a particular model writes a usable article
— that is what `scripts/llm_bench.py` measures against the real LM Studio.
"""

from __future__ import annotations

import dataclasses
import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import select

from adapters.factory import AdapterSettings, build_llm
from contracts.run import NodeStatus, RunStatus
from db.models import AgentOutput, ExecutionLog, ExecutionRun
from worker.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

MODEL = "qwen3-30b-a3b-instruct-2507"
ARTICLE = {
    "title": "Solar Energy in Saudi Arabia",
    "summary": "Saudi Arabia has some of the best sunlight on Earth. Here is what that means.",
    "article_md": "# Solar Energy in Saudi Arabia\n\nThe Kingdom's irradiance is among the world's highest [1].\n",
}


class FakeLMStudio(BaseHTTPRequestHandler):
    """POST /v1/chat/completions, streamed or not, as LM Studio answers it. Behaviour per server."""

    def log_message(self, *_args) -> None:  # keep pytest output clean
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body)
        if self.server.mode == "no-model":
            payload = json.dumps({"error": {"message": "No models loaded. Please load a model."}}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        text = json.dumps(ARTICLE)
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(text), 16):
                self._event({"choices": [{"index": 0, "delta": {"content": text[i : i + 16]}, "finish_reason": None}]})
            self._event({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n")
            return
        raise AssertionError("the Writer streams by default")

    def _event(self, data: dict) -> None:
        data |= {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": MODEL}
        self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
        self.wfile.flush()


@pytest.fixture()
def lm_studio() -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLMStudio)
    server.requests, server.mode = [], "ok"
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _local_llm(port: int):
    return build_llm(
        AdapterSettings(
            fake=False, llm_provider="local", llm_model=MODEL, llm_local_base_url=f"http://127.0.0.1:{port}/v1"
        )
    )


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]  # nothing listens once the socket is closed


def _writer_log(db, run_id) -> ExecutionLog:
    with db.sessions() as s:
        return s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.agent_type == "writer"))


async def test_the_blog_template_writes_its_article_with_a_local_model(db, store, registry, ports, lm_studio):
    run_id = db.start_run(db.unreviewed("Blog post"))
    ports = dataclasses.replace(ports, llm=_local_llm(lm_studio.server_address[1]))

    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.SUCCEEDED

    # ARTICLE is far shorter than medium's 800 words, so the Writer asks once for a fuller version;
    # the stand-in's second answer is no longer, so the first draft is what is kept.
    request, fuller = lm_studio.requests
    assert fuller["messages"][1]["content"].startswith("The article below is")
    assert request["model"] == MODEL
    assert request["stream"] is True
    assert request["response_format"]["type"] == "json_schema"
    assert set(request["response_format"]["json_schema"]["schema"]["required"]) == {"title", "summary", "article_md"}
    assert "Research notes:" in request["messages"][1]["content"]  # the Researcher's notes reached the prompt
    log = _writer_log(db, run_id)
    with db.sessions() as s:
        saved = s.scalars(select(AgentOutput).where(AgentOutput.log_id == log.id)).all()
    [article] = [o.content_json for o in saved if o.output_type == "text"]
    assert {k: article[k] for k in ARTICLE} == ARTICLE  # exactly what the model wrote, validated
    # and the files the Writer rendered from it itself (FR-04), never paths the model gave
    assert sorted(o.storage_path.rsplit(".", 1)[1] for o in saved if o.output_type == "file") == ["docx", "pdf"]
    assert article["pdf_path"].endswith(".pdf") and article["docx_path"].endswith(".docx")


async def test_with_lm_studio_stopped_the_writer_retries_then_says_what_to_do(db, store, registry, ports, sleeps):
    run_id = db.start_run(db.unreviewed("Blog post"))
    ports = dataclasses.replace(ports, llm=_local_llm(_closed_port()))

    assert await Orchestrator(store, registry, ports, sleep=sleeps).execute(run_id) == RunStatus.FAILED

    log = _writer_log(db, run_id)
    assert log.status == NodeStatus.FAILED
    assert log.retry_count == 3 and len(sleeps) == 3  # unreachable is retryable: it may be starting up
    assert "Is LM Studio's server running" in log.error_message


async def test_with_no_model_loaded_the_writer_fails_at_once(db, store, registry, ports, sleeps, lm_studio):
    lm_studio.mode = "no-model"
    run_id = db.start_run(db.unreviewed("Blog post"))
    ports = dataclasses.replace(ports, llm=_local_llm(lm_studio.server_address[1]))

    assert await Orchestrator(store, registry, ports, sleep=sleeps).execute(run_id) == RunStatus.FAILED

    log = _writer_log(db, run_id)
    assert sleeps == [] and len(lm_studio.requests) == 1  # retrying can't load a model
    assert "lms ls" in log.error_message
    with db.sessions() as s:
        assert s.get(ExecutionRun, run_id).status == RunStatus.FAILED
