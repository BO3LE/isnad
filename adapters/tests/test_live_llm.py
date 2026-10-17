"""Against a real model server — opt-in, never in CI. Skipped unless LIVE_LLM=1.

    LIVE_LLM=1 LLM_MODEL=<id from `lms ls`> python -m pytest adapters/tests/test_live_llm.py -v
    (LLM_BASE_URL defaults to LM Studio on this machine: http://localhost:1234/v1;
     a thinking model also needs LLM_REASONING_EFFORT=none, as the worker would have)

These check what a mock can't: that this server and this model accept the requests the adapter
sends, and answer them usably — streaming, a JSON Schema answer, and a tool call.
"""

from __future__ import annotations

import json
import os

import pytest

from adapters.llm.openai_compatible import LLMConfig, OpenAICompatibleLLM
from contracts.ports import Tool
from contracts.tools import run_tools

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_LLM") != "1", reason="LIVE_LLM=1 runs these against a real model")

SCHEMA = {
    "type": "object",
    "title": "Headline",
    "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["title", "summary"],
    "additionalProperties": False,
}


def _llm(**overrides) -> OpenAICompatibleLLM:
    model = os.environ.get("LLM_MODEL")
    if not model:
        pytest.fail("set LLM_MODEL to the id `lms ls` (or GET /v1/models) shows", pytrace=False)
    config = {
        "provider": "local",
        "base_url": os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        "model": model,
        "timeout_s": float(os.environ.get("LLM_TIMEOUT_S", "300")),
        "reasoning_effort": os.environ.get("LLM_REASONING_EFFORT") or None,
    }
    return OpenAICompatibleLLM(LLMConfig(**(config | overrides)))


async def test_the_server_offers_the_model():
    probe = await _llm().probe()
    assert probe["reachable"], probe
    assert probe["model_listed"], probe


@pytest.mark.parametrize("stream", [True, False], ids=["streamed", "whole"])
async def test_a_json_schema_answer_is_valid_json_of_that_shape(stream):
    llm = _llm(stream=stream)

    text = await llm.complete(
        "Give a headline and a one-sentence summary about solar energy in Saudi Arabia.",
        system="Answer with JSON only.",
        json_schema=SCHEMA,
    )

    answer = json.loads(text)
    assert set(answer) == {"title", "summary"} and all(isinstance(v, str) and v for v in answer.values())
    assert llm.last_usage.structured == "json_schema", "the server refused json_schema; the adapter fell back"


async def test_the_model_calls_a_tool_and_uses_the_result():
    tool = Tool(
        name="capacity_lookup",
        description="Installed solar capacity of a country, in gigawatts.",
        parameters={"type": "object", "properties": {"country": {"type": "string"}}, "required": ["country"]},
    )
    asked = []

    async def lookup(arguments):
        asked.append(arguments.get("country", ""))
        return {"installed_gw": 12.3}

    reply, _ = await run_tools(
        _llm(),
        [{"role": "user", "content": "Use the tool to find Saudi Arabia's installed solar capacity, then answer."}],
        {tool.name: (tool, lookup)},
    )

    assert any("saudi" in c.lower() for c in asked)
    assert "12.3" in reply.content
