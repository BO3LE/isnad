"""What reaches the API's logs: never the `code` or `state` Google sends back, nor any other token.

The access-log test runs the app under a real uvicorn server, since that is what writes the
request line — the test client never goes through uvicorn's access log.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from conftest import SETTINGS

from api.logs import redact_query
from api.main import create_app


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "/connections/google/callback?state=eyJ.abc.def&code=4/0Ab-xyz&scope=email",
            "/connections/google/callback?state=[redacted]&code=[redacted]&scope=email",
        ),
        ("/files/a.mp4?token=signed-123", "/files/a.mp4?token=[redacted]"),
        (
            "/x?Access_Token=a&refresh_token=b&id_token=c",
            "/x?Access_Token=[redacted]&refresh_token=[redacted]&id_token=[redacted]",
        ),
        ("/connections/google/start?mode=popup", "/connections/google/start?mode=popup"),
        ("/runs/123", "/runs/123"),
        ("/cb?mode=popup&code=", "/cb?mode=popup&code=[redacted]"),
    ],
)
def test_redact_query_blanks_the_values_of_secret_parameters_only(line, expected):
    assert redact_query(line) == expected


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _callback_lines(capture: _Capture) -> list[str]:
    return [entry for entry in capture.lines if "/connections/google/callback" in entry]


def test_uvicorns_access_log_never_shows_the_oauth_code_or_state():
    # The socket is bound here and handed to uvicorn, so no other process can take the port between
    # choosing it and serving on it. The waits are generous: a busy machine may be slow to start a
    # server or to answer, which says nothing about what the access log contains.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(SETTINGS), access_log=True))
    capture = _Capture()
    access = logging.getLogger("uvicorn.access")
    access.addHandler(capture)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert thread.is_alive(), "uvicorn stopped before it started"
            assert time.monotonic() < deadline, "uvicorn did not start within 30 s"
            time.sleep(0.05)
        response = httpx.get(
            f"http://127.0.0.1:{port}/connections/google/callback",
            params={"state": "CANARY-STATE-eyJhbGciOi", "code": "4/0CANARY-CODE"},
            follow_redirects=False,
            timeout=30,
        )
        assert response.status_code == 303  # refused (a forged state), but the request line was logged
        deadline = time.monotonic() + 10
        while not _callback_lines(capture) and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        access.removeHandler(capture)
        sock.close()

    lines = _callback_lines(capture)
    assert len(lines) == 1, f"expected one access-log line for the callback, got {len(lines)}"
    (line,) = lines
    assert "CANARY" not in line
    assert "state=[redacted]" in line
    assert "code=[redacted]" in line


def test_httpx_request_urls_are_not_logged_even_when_everything_else_logs_info():
    root, httpx_logger = logging.getLogger(), logging.getLogger("httpx")
    before = root.level, httpx_logger.level
    root.setLevel(logging.INFO)  # as uvicorn and Celery run
    httpx_logger.setLevel(logging.NOTSET)
    try:
        create_app(SETTINGS)
        assert not httpx_logger.isEnabledFor(logging.INFO)
    finally:
        root.setLevel(before[0])
        httpx_logger.setLevel(before[1])
