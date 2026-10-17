"""LLM_* environment → the Writer's LLM, and the one-line report the worker logs at startup."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from adapters.factory import MisconfiguredLLM, build_llm
from worker import celery_app
from worker.settings import WorkerSettings, adapter_settings

MODEL = "qwen3-30b-a3b-instruct-2507"


def _settings(monkeypatch, **env) -> WorkerSettings:
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return WorkerSettings(_env_file=None)


def test_the_environment_selects_a_local_model(monkeypatch):
    settings = _settings(
        monkeypatch,
        FAKE_ADAPTERS="false",
        LLM_PROVIDER="local",
        LLM_MODEL=MODEL,
        LLM_LOCAL_BASE_URL="http://host.docker.internal:1234/v1",
        LLM_TIMEOUT_S="600",
        LLM_STRUCTURED="json_object",
    )
    llm = build_llm(adapter_settings(settings))

    assert (llm.config.provider, llm.config.model, llm.config.base_url) == (
        "local",
        MODEL,
        "http://host.docker.internal:1234/v1",
    )
    assert llm.config.timeout_s == 600
    assert llm.config.structured == "json_object"


def test_empty_variables_count_as_unset(monkeypatch):
    # As .env.example ships them (`OPENAI_API_KEY=`), and as compose passes `${X:-}`.
    settings = _settings(monkeypatch, LLM_PROVIDER="", LLM_MODEL="", OPENAI_API_KEY="", LLM_BASE_URL="")

    assert settings.llm_provider is None and settings.openai_api_key is None and settings.llm_base_url is None
    llm = build_llm(adapter_settings(settings))
    assert isinstance(llm, MisconfiguredLLM)  # local by default, and it still needs LLM_MODEL
    assert "LLM_MODEL" in llm.message


class _Models(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        assert self.path == "/v1/models"
        body = json.dumps({"object": "list", "data": [{"id": MODEL, "object": "model", "created": 0, "owned_by": "x"}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture()
def models_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


def _closed_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}/v1"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"FAKE_ADAPTERS": "true"}, "LLM: fake (FAKE_ADAPTERS=true)"),
        (
            {"FAKE_ADAPTERS": "false", "LLM_PROVIDER": "openai"},
            "LLM: not usable — LLM_PROVIDER=openai needs OPENAI_API_KEY",
        ),
        ({"FAKE_ADAPTERS": "false", "LLM_MODEL": MODEL, "LLM_LOCAL_BASE_URL": "{closed}"}, "server not reachable"),
        ({"FAKE_ADAPTERS": "false", "LLM_MODEL": MODEL, "LLM_LOCAL_BASE_URL": "{up}"}, " — ready"),
        (
            {"FAKE_ADAPTERS": "false", "LLM_MODEL": "gpt-oss-20b", "LLM_LOCAL_BASE_URL": "{up}"},
            "doesn't list that model",
        ),
    ],
    ids=["fake", "no-key", "lm-studio-stopped", "ready", "model-not-downloaded"],
)
def test_the_startup_report(monkeypatch, models_server, env, expected):
    env = {k: v.format(closed=_closed_url(), up=models_server) for k, v in env.items()}
    monkeypatch.setattr(celery_app, "settings", _settings(monkeypatch, **env))

    report = celery_app.check_llm()

    assert expected in report


def test_the_startup_report_never_shows_a_key(monkeypatch):
    settings = _settings(
        monkeypatch,
        FAKE_ADAPTERS="false",
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="or-secret-key",
        LLM_MODEL="m",
        LLM_BASE_URL=_closed_url(),
    )
    monkeypatch.setattr(celery_app, "settings", settings)

    assert "or-secret-key" not in celery_app.check_llm()
