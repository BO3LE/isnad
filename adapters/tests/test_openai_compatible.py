"""OpenAICompatibleLLM against a scripted OpenAI-compatible server (httpx.MockTransport).

The real `openai` SDK builds every request and parses every response, streamed or not, so these
tests exercise what LM Studio, Ollama, OpenAI and OpenRouter will actually be sent.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from adapters.llm.openai_compatible import LLMConfig, OpenAICompatibleLLM, portable_schema, strip_thinking
from contracts.errors import AgentError
from contracts.ports import Tool, ToolCallingLLMPort
from contracts.tools import run_tools

SCHEMA = {
    "additionalProperties": False,
    "properties": {
        "title": {"maxLength": 200, "minLength": 1, "title": "title", "type": "string"},
        "summary": {"minLength": 1, "title": "summary", "type": "string"},
    },
    "required": ["title", "summary"],
    "title": "WriteOutput",
    "type": "object",
}
ANSWER = {"title": "Solar in Riyadh", "summary": "Sunny."}


def completion(content: str | None = None, *, finish: str = "stop", tool_calls: list | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def chunk(content: str | None = None, finish: str | None = None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def sse(*events: dict) -> bytes:
    return b"".join(f"data: {json.dumps(e)}\n\n".encode() for e in events) + b"data: [DONE]\n\n"


def error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message, "type": "invalid_request_error"}})


class Server:
    """Answers each request with the next scripted response and records every request body."""

    def __init__(self, *responses: httpx.Response | Exception):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.content]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def llm_for(server: Server, **overrides) -> OpenAICompatibleLLM:
    config = LLMConfig(
        **{"provider": "local", "base_url": "http://lmstudio.test/v1", "model": "qwen3-30b-a3b", "stream": False}
        | overrides
    )
    return OpenAICompatibleLLM(config, http_client=httpx.AsyncClient(transport=httpx.MockTransport(server.handle)))


# ---------------------------------------------------------------- requests
async def test_a_schema_is_sent_as_a_strict_portable_json_schema():
    server = Server(httpx.Response(200, json=completion(json.dumps(ANSWER))))

    text = await llm_for(server).complete("Write.", system="Be careful.", json_mode=True, json_schema=SCHEMA)

    assert json.loads(text) == ANSWER
    (request,) = server.requests
    assert str(request.url) == "http://lmstudio.test/v1/chat/completions"
    body = server.bodies[0]
    assert body["model"] == "qwen3-30b-a3b"
    assert body["messages"] == [{"role": "system", "content": "Be careful."}, {"role": "user", "content": "Write."}]
    assert body["max_tokens"] == 4096
    assert "temperature" not in body  # the model preset's own default
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "WriteOutput",
            "strict": True,
            "schema": {
                "additionalProperties": False,
                "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
                "required": ["title", "summary"],
                "type": "object",
            },
        },
    }


async def test_json_mode_without_a_schema_asks_for_a_json_object():
    server = Server(httpx.Response(200, json=completion("{}")))

    await llm_for(server).complete("Write.", json_mode=True)

    assert server.bodies[0]["response_format"] == {"type": "json_object"}


async def test_plain_text_sends_no_response_format():
    server = Server(httpx.Response(200, json=completion("Hello.")))

    assert await llm_for(server).complete("Say hello.") == "Hello."
    assert "response_format" not in server.bodies[0]


async def test_openai_gets_max_completion_tokens_and_the_key_as_a_bearer_token():
    server = Server(httpx.Response(200, json=completion("Hi.")))
    llm = llm_for(server, provider="openai", base_url="https://api.openai.test/v1", api_key="sk-test-key")

    await llm.complete("Hi.")

    assert server.bodies[0]["max_completion_tokens"] == 4096
    assert "max_tokens" not in server.bodies[0]
    assert server.requests[0].headers["authorization"] == "Bearer sk-test-key"


async def test_a_stray_openai_base_url_in_the_environment_is_ignored(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-the-environment")
    server = Server(httpx.Response(200, json=completion("Hi.")))

    await llm_for(server).complete("Hi.")

    assert server.requests[0].url.host == "lmstudio.test"
    assert "sk-from-the-environment" not in server.requests[0].headers.get("authorization", "")


# ---------------------------------------------------------------- streaming
async def test_a_streamed_answer_is_assembled_and_measured():
    body = sse(
        chunk("<think>plan</think>"), chunk('{"title": "Sol'), chunk('ar", "summary": "S."}'), chunk(finish="stop")
    )
    server = Server(httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body))
    llm = llm_for(server, stream=True)

    text = await llm.complete("Write.", json_schema=SCHEMA)

    assert json.loads(text) == {"title": "Solar", "summary": "S."}
    assert server.bodies[0]["stream"] is True
    assert "stream_options" not in server.bodies[0]  # local servers vary in what they accept
    assert llm.last_usage.chunks == 3
    assert llm.last_usage.finish_reason == "stop"
    assert llm.last_usage.first_token_seconds is not None
    assert llm.last_usage.structured == "json_schema"


async def test_hosted_providers_are_asked_for_usage_on_a_stream():
    body = sse(chunk("Hi."), chunk(finish="stop"))
    server = Server(httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body))

    await llm_for(server, provider="openrouter", api_key="k", stream=True).complete("Hi.")

    assert server.bodies[0]["stream_options"] == {"include_usage": True}


async def test_a_stream_that_outlives_the_deadline_is_a_timeout():
    async def slow():
        yield f"data: {json.dumps(chunk('He'))}\n\n".encode()
        await asyncio.sleep(5)
        yield b"data: [DONE]\n\n"

    server = Server(httpx.Response(200, headers={"content-type": "text/event-stream"}, content=slow()))

    with pytest.raises(AgentError) as failed:
        await llm_for(server, stream=True, timeout_s=0.3).complete("Write.")
    assert failed.value.code == "llm_timeout"
    assert not failed.value.retryable  # locally, a retry repeats the same wait


# ---------------------------------------------------------------- what comes back
@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ('<think>\nweighing it up\n</think>\n\n{"a": 1}', '{"a": 1}'),
        ("<THINK>x</THINK>Answer", "Answer"),
        ("<think>never finished", ""),
        ("No thinking here.", "No thinking here."),
    ],
)
def test_strip_thinking(raw, clean):
    assert strip_thinking(raw) == clean


async def test_an_answer_cut_off_by_the_token_limit_is_not_passed_on():
    server = Server(httpx.Response(200, json=completion('{"title": "Sol', finish="length")))

    with pytest.raises(AgentError) as failed:
        await llm_for(server, max_output_tokens=64).complete("Write.", json_schema=SCHEMA)
    assert failed.value.code == "llm_truncated"
    assert not failed.value.retryable
    assert "64" in failed.value.message


async def test_an_empty_answer_is_retryable():
    server = Server(httpx.Response(200, json=completion("<think>only thoughts</think>")))

    with pytest.raises(AgentError) as failed:
        await llm_for(server).complete("Write.")
    assert failed.value.code == "llm_empty"
    assert failed.value.retryable


# ---------------------------------------------------------------- structured-output fallback
async def test_a_server_that_refuses_json_schema_is_asked_again_more_simply_and_that_is_remembered():
    server = Server(
        error(400, "This server does not support response_format json_schema"),
        error(400, "response_format json_object is not supported"),
        httpx.Response(200, json=completion(json.dumps(ANSWER))),
        httpx.Response(200, json=completion(json.dumps(ANSWER))),
    )
    llm = llm_for(server)

    assert json.loads(await llm.complete("Write.", json_schema=SCHEMA)) == ANSWER
    assert [b.get("response_format", {}).get("type") for b in server.bodies] == ["json_schema", "json_object", None]
    assert llm.last_usage.structured == "none"

    await llm.complete("Again.", json_schema=SCHEMA)
    assert "response_format" not in server.bodies[3]  # starts from what this server accepted


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("Trying to keep the first 20000 tokens when context the overflows. n_ctx: 4096", "llm_context"),
        (
            "No models loaded. Please load a model in the developer page or use the `lms load` command.",
            "llm_model_missing",
        ),
    ],
)
async def test_a_400_that_a_simpler_format_cannot_fix_is_not_retried_with_one(message, code):
    server = Server(error(400, message))

    with pytest.raises(AgentError) as failed:
        await llm_for(server).complete("Write.", json_schema=SCHEMA)
    assert failed.value.code == code
    assert not failed.value.retryable
    assert len(server.requests) == 1


# ---------------------------------------------------------------- errors
@pytest.mark.parametrize(
    ("response", "code", "retryable", "says"),
    [
        (error(401, "Incorrect API key provided: sk-test-****"), "llm_auth", False, "LLM_API_KEY"),
        (error(403, "forbidden"), "llm_auth", False, "LLM_API_KEY"),
        (error(404, "model 'qwen3-30b-a3b' not found"), "llm_model_missing", False, "lms ls"),
        (error(429, "slow down"), "llm_rate_limited", True, "busy"),
        (error(500, "boom"), "llm_server_error", True, "HTTP 500"),
        (error(503, "loading"), "llm_server_error", True, "HTTP 503"),
        (error(422, "unprocessable"), "llm_bad_request", False, "unprocessable"),
        (httpx.ConnectError("Connection refused"), "llm_unreachable", True, "lms server start"),
        (httpx.ReadTimeout("timed out"), "llm_timeout", False, "LLM_TIMEOUT_S"),
    ],
    ids=["401", "403", "404", "429", "500", "503", "422", "refused", "read-timeout"],
)
async def test_each_failure_becomes_a_readable_agent_error_after_exactly_one_request(response, code, retryable, says):
    server = Server(response)

    with pytest.raises(AgentError) as failed:
        await llm_for(server, api_key="sk-test-key").complete("Write.")

    assert failed.value.code == code
    assert failed.value.retryable is retryable
    assert says in failed.value.message
    assert "sk-test-key" not in failed.value.message
    assert len(server.requests) == 1  # no SDK retries: the orchestrator owns retrying


async def test_a_hosted_provider_timeout_is_retryable():
    server = Server(httpx.ReadTimeout("timed out"))

    with pytest.raises(AgentError) as failed:
        await llm_for(server, provider="openai", base_url="https://api.openai.test/v1", api_key="k").complete("Hi.")
    assert failed.value.retryable
    assert "lms" not in failed.value.message


# ---------------------------------------------------------------- tool calling
LOOKUP = Tool(
    name="lookup",
    description="Find a fact.",
    parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
)


async def test_tools_are_offered_and_the_models_calls_come_back_parsed():
    calls = [
        {"id": "call_a", "type": "function", "function": {"name": "lookup", "arguments": '{"q": "irradiance"}'}},
        {"type": "function", "function": {"name": "lookup", "arguments": "{q: broken"}},
    ]
    server = Server(httpx.Response(200, json=completion(None, finish="tool_calls", tool_calls=calls)))
    llm = llm_for(server, stream=True)  # tool calls are never streamed

    reply = await llm.chat([{"role": "user", "content": "?"}], tools=[LOOKUP])

    assert isinstance(llm, ToolCallingLLMPort)
    assert server.bodies[0]["tools"] == [
        {
            "type": "function",
            "function": {"name": "lookup", "description": "Find a fact.", "parameters": LOOKUP.parameters},
        }
    ]
    assert "stream" not in server.bodies[0] or server.bodies[0]["stream"] is False
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("call_a", "lookup", {"q": "irradiance"}),
        ("call_1", "lookup", {"_unparsed": "{q: broken"}),
    ]


async def test_run_tools_through_the_adapter_end_to_end():
    call = {"id": "call_a", "type": "function", "function": {"name": "lookup", "arguments": '{"q": "GHI"}'}}
    server = Server(
        httpx.Response(200, json=completion(None, finish="tool_calls", tool_calls=[call])),
        httpx.Response(200, json=completion("About 2,200 kWh/m² a year.")),
    )
    looked_up = []

    async def lookup(arguments):
        looked_up.append(arguments["q"])
        return {"ghi_kwh_m2_year": 2200}

    reply, _ = await run_tools(llm_for(server), [{"role": "user", "content": "GHI?"}], {"lookup": (LOOKUP, lookup)})

    assert reply.content == "About 2,200 kWh/m² a year."
    assert looked_up == ["GHI"]
    second = server.bodies[1]["messages"]
    assert second[1]["tool_calls"][0]["function"]["name"] == "lookup"
    assert second[2] == {"role": "tool", "tool_call_id": "call_a", "content": '{"ghi_kwh_m2_year": 2200}'}


# ---------------------------------------------------------------- readiness
async def test_probe_reports_whether_the_model_is_offered():
    models = {"object": "list", "data": [{"id": "qwen3-30b-a3b", "object": "model", "created": 0, "owned_by": "me"}]}
    server = Server(httpx.Response(200, json=models), httpx.Response(200, json=models))

    assert (await llm_for(server).probe())["model_listed"] is True
    assert (await llm_for(server, model="gpt-oss-20b").probe()) == {
        "reachable": True,
        "model_listed": False,
        "models": ["qwen3-30b-a3b"],
    }


async def test_probe_never_raises():
    server = Server(httpx.ConnectError("refused"))

    assert await llm_for(server).probe() == {"reachable": False, "model_listed": False, "error": "APIConnectionError"}


def test_a_schema_with_optional_fields_is_sent_without_strict():
    schema, strict = portable_schema({"type": "object", "properties": {"a": {"type": "string"}}, "required": []})
    assert schema["additionalProperties"] is False
    assert strict is False
