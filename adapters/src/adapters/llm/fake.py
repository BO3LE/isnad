from __future__ import annotations

import json


class FakeLLM:
    """Canned, deterministic responses. Costs nothing; used in tests, CI and FAKE_ADAPTERS mode."""

    def __init__(self, response: str | None = None):
        self._response = response
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        self.prompts.append(prompt)
        if self._response is not None:
            return self._response
        if json_mode:
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
