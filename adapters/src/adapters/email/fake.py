from __future__ import annotations

import uuid


class FakeEmail:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str]] = []

    async def send(self, to: list[str], subject: str, body: str) -> str:
        self.sent.append((to, subject, body))
        return f"fake-{uuid.uuid4().hex[:12]}"
