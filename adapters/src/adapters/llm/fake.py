from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from contracts.ports import ChatReply, Tool


class FakeLLM:
    """Canned, deterministic responses. Costs nothing; used in tests, CI and FAKE_ADAPTERS mode.

    `chat_replies` scripts `chat()` (tool calling): one reply per call, in order.
    """

    def __init__(self, response: str | None = None, *, chat_replies: Sequence[ChatReply] = ()):
        self._response = response
        self._chat_replies = list(chat_replies)
        self.prompts: list[str] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self.prompts.append(prompt)
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode, "json_schema": json_schema})
        if self._response is not None:
            return self._response
        if json_mode or json_schema is not None:
            return json.dumps(
                {
                    "title": "The Future of Solar Energy in Saudi Arabia",
                    "summary": "A short, sourced overview of where solar stands today and what comes next.",
                    "article_md": (
                        "# The Future of Solar Energy in Saudi Arabia\n\n"
                        "Saudi Arabia receives some of the strongest sunlight on Earth. "
                        "This article is canned output from the fake LLM adapter.\n"
                    ),
                }
            )
        return "Canned text from the fake LLM adapter."

    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[Tool] = (),
        json_schema: dict[str, Any] | None = None,
    ) -> ChatReply:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": [t.name for t in tools]})
        if self._chat_replies:
            return self._chat_replies.pop(0)
        return ChatReply(content="Canned text from the fake LLM adapter.", finish_reason="stop")
