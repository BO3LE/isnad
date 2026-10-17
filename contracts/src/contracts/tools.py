"""The tool-calling loop an agent can use with a `ToolCallingLLMPort`.

The model answers either with text or with calls to the tools it was given. Each call is run, its
result handed back as a `tool` message, and the model asked again — until it answers in text or
`max_rounds` is reached. A call to a tool that doesn't exist, with arguments that don't parse, or
whose handler fails, is answered with an error the model can read and correct; a handler that
raises `AgentError` stops the loop, since that is a failure the person should see.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from contracts.errors import AgentError
from contracts.ports import ChatReply, Tool, ToolCall, ToolCallingLLMPort

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


async def run_tools(
    llm: ToolCallingLLMPort,
    messages: Sequence[dict[str, Any]],
    tools: Mapping[str, tuple[Tool, Handler]],
    *,
    max_rounds: int = 4,
    json_schema: dict[str, Any] | None = None,
) -> tuple[ChatReply, list[dict[str, Any]]]:
    """Run the loop. Returns the final text reply and the whole conversation, tool calls included."""
    conversation = [dict(m) for m in messages]
    specs = [spec for spec, _ in tools.values()]
    for _ in range(max_rounds):
        reply = await llm.chat(conversation, tools=specs, json_schema=json_schema)
        if not reply.tool_calls:
            return reply, conversation
        conversation.append(_assistant_turn(reply))
        for call in reply.tool_calls:
            conversation.append({"role": "tool", "tool_call_id": call.id, "content": await _run(call, tools)})
    raise AgentError(
        f"The model was still calling tools after {max_rounds} rounds.", code="llm_tool_loop", retryable=False
    )


async def _run(call: ToolCall, tools: Mapping[str, tuple[Tool, Handler]]) -> str:
    if call.name not in tools:
        return _error(f"There is no tool named {call.name!r}. Available: {', '.join(sorted(tools))}.")
    if "_unparsed" in call.arguments:
        return _error("The arguments were not valid JSON. Send them again as a JSON object.")
    _, handler = tools[call.name]
    try:
        result = await handler(call.arguments)
    except AgentError:
        raise
    except Exception as exc:  # the model sent arguments the handler can't use — let it try again
        return _error(f"{type(exc).__name__}: {str(exc)[:200]}")
    return result if isinstance(result, str) else json.dumps(result, default=str)


def _error(message: str) -> str:
    return json.dumps({"error": message})


def _assistant_turn(reply: ChatReply) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": reply.content or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": _raw(call)},
            }
            for call in reply.tool_calls
        ],
    }


def _raw(call: ToolCall) -> str:
    unparsed = call.arguments.get("_unparsed")
    return unparsed if isinstance(unparsed, str) else json.dumps(call.arguments)
