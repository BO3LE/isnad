"""A small SMTP server for tests (as worker.testing is for the run store), standard library only:
enough of RFC 5321 for smtplib. Nothing imports it outside tests.

`mode` says how it answers: "ok", "auth" (refuses the login), "busy" (451 after the message),
"reject" (554 after the message), "drop" (takes the message, then hangs up without answering),
"bad-quit" (500 to QUIT after a delivered message). `refuse` lists recipients answered with 550.
Every message it was given is kept in `messages`, whatever it answered.
"""

from __future__ import annotations

import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager


class _Handler(socketserver.StreamRequestHandler):
    def _send(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        server = self.server
        self._send("220 test ESMTP")
        while line := self.rfile.readline():
            command = line.decode().strip()
            verb = command.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self.wfile.write(b"250-test\r\n250-AUTH PLAIN\r\n250 8BITMIME\r\n")
            elif verb == "AUTH":
                self._send("535 authentication failed" if server.mode == "auth" else "235 ok")
            elif verb in ("MAIL", "RSET", "NOOP"):
                self._send("250 ok")
            elif verb == "RCPT":
                address = command.split(":", 1)[1].strip().strip("<>")
                self._send("550 no such user" if address in server.refuse else "250 ok")
            elif verb == "DATA":
                self._send("354 end with .")
                body = []
                while (part := self.rfile.readline()) not in (b".\r\n", b""):
                    body.append(part)
                server.messages.append(b"".join(body))
                if server.mode == "drop":
                    return  # hang up: the client never hears whether it was taken
                self._send({"busy": "451 try again later", "reject": "554 rejected"}.get(server.mode, "250 queued"))
            elif verb == "QUIT":
                self._send("500 broken" if server.mode == "bad-quit" else "221 bye")
                return
            else:
                self._send("502 not implemented")


class SmtpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.mode = "ok"
        self.refuse: set[str] = set()
        self.messages: list[bytes] = []

    @property
    def port(self) -> int:
        return self.server_address[1]


@contextmanager
def smtp_server() -> Iterator[SmtpServer]:
    server = SmtpServer()
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
