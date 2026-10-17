"""contracts.tools.run_tools: the loop that lets a model call an agent's tools and read the results."""

from __future__ import annotations

import json

import pytest

from contracts.errors import AgentError
from contracts.ports import ChatReply, Tool, ToolCall, ToolCallingLLMPort
from contracts.tools import run_tools

WEATHER = Tool(
    name="weather",
    description="Today's weather in a city.",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)


class Scripted:
    """A model that answers from a script and records what it was sent."""

    def __init__(self, *replies: ChatReply):
        self.replies = list(replies)
        self.sent: list[list[dict]] = []

    async def chat(self, messages, *, tools=(), json_schema=None):
        self.sent.append([dict(m) for m in messages])
        assert [t.name for t in tools] == ["weather"]
        return self.replies.pop(0)


def _call(name="weather", arguments=None, id="call_1"):
    return ToolCall(id=id, name=name, arguments={"city": "Riyadh"} if arguments is None else arguments)


async def _weather(arguments):
    return {"city": arguments["city"], "high_c": 41}


TOOLS = {"weather": (WEATHER, _weather)}
ASK = [{"role": "user", "content": "How hot is it in Riyadh?"}]


def test_a_scripted_model_counts_as_a_tool_calling_llm():
    assert isinstance(Scripted(), ToolCallingLLMPort)


async def test_the_model_calls_a_tool_reads_the_result_and_answers():
    llm = Scripted(ChatReply("", (_call(),), "tool_calls"), ChatReply("41°C in Riyadh today.", (), "stop"))

    reply, conversation = await run_tools(llm, ASK, TOOLS)

    assert reply.content == "41°C in Riyadh today."
    assistant, result = conversation[1], conversation[2]
    assert assistant["tool_calls"][0]["function"] == {"name": "weather", "arguments": '{"city": "Riyadh"}'}
    assert result == {"role": "tool", "tool_call_id": "call_1", "content": '{"city": "Riyadh", "high_c": 41}'}
    assert llm.sent[1] == conversation  # the second request carries the call and its result


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (_call(name="forecast"), "There is no tool named 'forecast'"),
        (_call(arguments={"_unparsed": "{city: Riyadh"}), "not valid JSON"),
        (_call(arguments={"town": "Riyadh"}), "KeyError"),
    ],
    ids=["unknown-tool", "unparsed-arguments", "handler-rejects-arguments"],
)
async def test_a_bad_call_is_answered_with_an_error_the_model_can_correct(call, expected):
    llm = Scripted(ChatReply("", (call,), "tool_calls"), ChatReply("Sorry — 41°C.", (), "stop"))

    reply, conversation = await run_tools(llm, ASK, TOOLS)

    assert reply.content == "Sorry — 41°C."
    assert expected in json.loads(conversation[2]["content"])["error"]


async def test_unparsed_arguments_go_back_to_the_model_exactly_as_it_sent_them():
    llm = Scripted(ChatReply("", (_call(arguments={"_unparsed": "{city: Riyadh"}),)), ChatReply("ok"))

    _, conversation = await run_tools(llm, ASK, TOOLS)

    assert conversation[1]["tool_calls"][0]["function"]["arguments"] == "{city: Riyadh"


async def test_a_tool_that_raises_an_agent_error_stops_the_loop():
    async def expired(_arguments):
        raise AgentError("Your Google connection has expired.", retryable=False)

    llm = Scripted(ChatReply("", (_call(),)))

    with pytest.raises(AgentError, match="expired"):
        await run_tools(llm, ASK, {"weather": (WEATHER, expired)})


async def test_a_model_that_never_stops_calling_tools_is_cut_off():
    llm = Scripted(*[ChatReply("", (_call(id=f"c{i}"),)) for i in range(3)])

    with pytest.raises(AgentError) as stopped:
        await run_tools(llm, ASK, TOOLS, max_rounds=3)
    assert stopped.value.code == "llm_tool_loop"
    assert not stopped.value.retryable
