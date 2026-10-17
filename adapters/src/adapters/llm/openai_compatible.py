"""LLMPort for any OpenAI-compatible Chat Completions server.

One adapter for every provider, chosen by LLM_PROVIDER (see `adapters.factory`):

    local       LM Studio (http://localhost:1234/v1) or Ollama (http://localhost:11434/v1) on this
                machine. No key, no per-token cost.
    openai      api.openai.com, with OPENAI_API_KEY / LLM_API_KEY.
    openrouter  openrouter.ai, with OPENROUTER_API_KEY / LLM_API_KEY.

What it adds over a bare SDK call:

- The base URL is always passed explicitly, so an empty or stray OPENAI_BASE_URL in the environment
  can't redirect requests.
- Structured output: a schema is sent as `response_format: json_schema` (LM Studio and Ollama then
  constrain decoding to it). A server that refuses that mode is asked again with `json_object`, then
  with no response_format at all — and the mode that worked is kept for later calls.
- `<think>…</think>` blocks that reasoning models emit are removed from the answer.
- LLM_REASONING_EFFORT is sent as `reasoning_effort` when set. `none` turns a thinking model's
  reasoning off in LM Studio — the Writer doesn't need it, and a slow local model can spend its whole
  LLM_MAX_OUTPUT_TOKENS thinking. Unset, nothing is sent and the server's default applies.
- Streaming, so a long local generation is bounded by one overall deadline (LLM_TIMEOUT_S), not by
  a per-request read timeout that the first token alone can exceed.
- No SDK retries (`max_retries=0`): the orchestrator owns retrying. Errors become AgentErrors with a
  readable message and the right `retryable`.
- Tool calling (`chat`), for `contracts.tools.run_tools`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import ChatReply, Tool, ToolCall

log = logging.getLogger(__name__)

Provider = Literal["local", "openai", "openrouter"]
Structured = Literal["json_schema", "json_object", "none"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
_FALLBACK: dict[str, Structured] = {"json_schema": "json_object", "json_object": "none"}

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_SCHEMA_NAME = re.compile(r"[^A-Za-z0-9_-]")
# Keywords some providers' strict JSON Schema modes reject. The agent validates them afterwards anyway.
_UNPORTABLE = {"title", "default", "examples", "minLength", "maxLength", "$schema"}


@dataclass(frozen=True)
class LLMConfig:
    provider: Provider
    base_url: str
    model: str
    api_key: str | None = None
    structured: Structured = "json_schema"
    timeout_s: float = 300.0
    max_output_tokens: int = 4096
    temperature: float | None = None  # None: the server's (or the model preset's) default
    stream: bool = True
    reasoning_effort: ReasoningEffort | None = None  # None: not sent — the server's default

    @property
    def is_local(self) -> bool:
        return self.provider == "local"


@dataclass
class Usage:
    """What the last call cost, for the benchmark and the worker log. Never contains text."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    seconds: float = 0.0
    first_token_seconds: float | None = None
    structured: Structured | None = None
    finish_reason: str | None = None
    chunks: int = 0
    reasoning_chunks: int = 0  # streamed pieces of reasoning (counted, never kept)


class OpenAICompatibleLLM:
    """Implements `LLMPort` and `ToolCallingLLMPort`."""

    def __init__(self, config: LLMConfig, *, http_client: httpx.AsyncClient | None = None):
        from openai import AsyncOpenAI

        if not config.base_url:
            raise ValueError("LLMConfig.base_url is required")
        self.config = config
        self._structured: Structured = config.structured
        self.last_usage = Usage()
        self._client = AsyncOpenAI(
            # LM Studio and Ollama ignore the key, but the SDK insists on one.
            api_key=config.api_key or "not-needed-for-a-local-model",
            base_url=config.base_url,
            max_retries=0,
            timeout=httpx.Timeout(config.timeout_s, connect=10.0),
            http_client=http_client,
        )

    # ------------------------------------------------------------------ LLMPort
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        wants_json = json_mode or json_schema is not None
        message, finish = await self._with_structured_fallback(messages, wants_json, json_schema, tools=())
        text = strip_thinking(message.get("content") or "")
        if finish == "length":
            if not text and self._thought(message):
                raise self._thinking_only()
            raise NonRetryableAgentError(
                f"The model's answer was cut off at {self.config.max_output_tokens} tokens "
                "(LLM_MAX_OUTPUT_TOKENS). Raise it, or ask for a shorter text.",
                code="llm_truncated",
            )
        if not text.strip():
            raise AgentError("The model returned an empty answer.", code="llm_empty")
        return text

    # ------------------------------------------------------------------ ToolCallingLLMPort
    async def chat(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[Tool] = (),
        json_schema: dict[str, Any] | None = None,
    ) -> ChatReply:
        message, finish = await self._with_structured_fallback(
            list(messages), json_schema is not None, json_schema, tools=tools
        )
        calls = tuple(_tool_call(raw, i) for i, raw in enumerate(message.get("tool_calls") or []))
        content = strip_thinking(message.get("content") or "")
        if finish == "length" and not calls:
            if not content and self._thought(message):
                raise self._thinking_only()
            raise NonRetryableAgentError(
                f"The model's answer was cut off at {self.config.max_output_tokens} tokens (LLM_MAX_OUTPUT_TOKENS).",
                code="llm_truncated",
            )
        return ChatReply(content=content, tool_calls=calls, finish_reason=finish)

    # ------------------------------------------------------------------ readiness
    async def probe(self) -> dict[str, Any]:
        """Is the server up, and does it offer the configured model? Never raises."""
        try:
            listed = await asyncio.wait_for(self._model_ids(), timeout=10)
        except Exception as exc:
            return {"reachable": False, "model_listed": False, "error": type(exc).__name__}
        return {"reachable": True, "model_listed": self.config.model in listed, "models": listed[:25]}

    async def _model_ids(self) -> list[str]:
        return [model.id async for model in self._client.models.list()]

    # ------------------------------------------------------------------ internals
    async def _with_structured_fallback(
        self,
        messages: list[dict[str, Any]],
        wants_json: bool,
        json_schema: dict[str, Any] | None,
        *,
        tools: Sequence[Tool],
    ) -> tuple[dict[str, Any], str | None]:
        import openai

        mode = self._structured
        while True:
            response_format = _response_format(mode, wants_json, json_schema)
            try:
                result = await self._call(messages, response_format, tools)
            except openai.BadRequestError as exc:
                weaker = _FALLBACK.get(mode)
                if (
                    response_format is None
                    or weaker is None
                    or _is_context_overflow(exc)
                    or _mentions_missing_model(exc)
                ):
                    raise self._mapped(exc) from exc
                log.warning("the LLM server refused response_format %s; trying %s", mode, weaker)
                mode = weaker
                continue
            except Exception as exc:
                raise self._mapped(exc) from exc
            if mode != self._structured:
                self._structured = mode  # remembered: later calls start from what this server accepts
            self.last_usage.structured = mode if wants_json else None
            return result

    async def _call(
        self, messages: list[dict[str, Any]], response_format: dict[str, Any] | None, tools: Sequence[Tool]
    ) -> tuple[dict[str, Any], str | None]:
        params: dict[str, Any] = {"model": self.config.model, "messages": messages}
        # OpenAI's newer models only take max_completion_tokens; local servers and OpenRouter take max_tokens.
        token_param = "max_completion_tokens" if self.config.provider == "openai" else "max_tokens"
        params[token_param] = self.config.max_output_tokens
        if self.config.temperature is not None:
            params["temperature"] = self.config.temperature
        if self.config.reasoning_effort is not None:
            params["reasoning_effort"] = self.config.reasoning_effort
        if response_format is not None:
            params["response_format"] = response_format
        if tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        self.last_usage = Usage()
        started = time.monotonic()
        async with asyncio.timeout(self.config.timeout_s):
            if self.config.stream and not tools:
                result = await self._streamed(params, started)
            else:
                response = await self._client.chat.completions.create(**params)
                choice = response.choices[0]
                result = (choice.message.model_dump(exclude_none=True), choice.finish_reason)
                if _reasoning(choice.message):
                    self.last_usage.reasoning_chunks = 1
                if response.usage is not None:
                    self.last_usage.prompt_tokens = response.usage.prompt_tokens
                    self.last_usage.completion_tokens = response.usage.completion_tokens
        self.last_usage.seconds = time.monotonic() - started
        self.last_usage.finish_reason = result[1]
        return result

    async def _streamed(self, params: dict[str, Any], started: float) -> tuple[dict[str, Any], str | None]:
        if self.config.provider != "local":  # documented on both; local servers vary
            params["stream_options"] = {"include_usage": True}
        stream = await self._client.chat.completions.create(**params, stream=True)
        parts: list[str] = []
        finish: str | None = None
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    self.last_usage.prompt_tokens = chunk.usage.prompt_tokens
                    self.last_usage.completion_tokens = chunk.usage.completion_tokens
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta is not None and _reasoning(choice.delta):
                    self.last_usage.reasoning_chunks += 1
                if choice.delta is not None and choice.delta.content:
                    if self.last_usage.first_token_seconds is None:
                        self.last_usage.first_token_seconds = time.monotonic() - started
                    parts.append(choice.delta.content)
                    self.last_usage.chunks += 1
                if choice.finish_reason:
                    finish = choice.finish_reason
        finally:
            await stream.close()
        return {"role": "assistant", "content": "".join(parts)}, finish

    def _thought(self, message: dict[str, Any]) -> bool:
        """Did the model reason — in a separate field, or in an unclosed `<think>` — before it was cut off?"""
        return self.last_usage.reasoning_chunks > 0 or bool(re.match(r"\s*<think>", message.get("content") or "", re.I))

    def _thinking_only(self) -> NonRetryableAgentError:
        # Not llm_truncated: asking again would spend the same tokens thinking.
        return NonRetryableAgentError(
            f"The model spent all {self.config.max_output_tokens} tokens (LLM_MAX_OUTPUT_TOKENS) thinking and "
            "never answered. Set LLM_REASONING_EFFORT=none to turn its thinking off, or raise the limit.",
            code="llm_thinking",
        )

    def _mapped(self, exc: BaseException) -> AgentError:
        """A provider failure, as a message the person can act on. Never quotes a key."""
        import openai

        cfg = self.config
        where = f"the local model server at {cfg.base_url}" if cfg.is_local else f"the {cfg.provider} API"
        if isinstance(exc, AgentError):
            return exc
        if isinstance(exc, openai.APITimeoutError | TimeoutError):
            # Locally a timeout means this machine is too slow for the request; repeating it repeats the wait.
            return AgentError(
                f"The model didn't finish within {cfg.timeout_s:.0f} seconds (LLM_TIMEOUT_S). "
                "Raise it, or ask for a shorter text.",
                code="llm_timeout",
                retryable=not cfg.is_local,
            )
        if isinstance(exc, openai.APIConnectionError):
            hint = " Is LM Studio's server running (`lms server start`)?" if cfg.is_local else ""
            return AgentError(f"Couldn't reach {where}.{hint}", code="llm_unreachable")
        if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
            return NonRetryableAgentError(f"{where.capitalize()} refused the API key (LLM_API_KEY).", code="llm_auth")
        if isinstance(exc, openai.NotFoundError) or _mentions_missing_model(exc):
            hint = " Download or load it in LM Studio, or set LLM_MODEL to one `lms ls` lists." if cfg.is_local else ""
            return NonRetryableAgentError(
                f"The model “{cfg.model}” isn't available from {where}.{hint}", code="llm_model_missing"
            )
        if isinstance(exc, openai.RateLimitError):
            return AgentError(f"{where.capitalize()} is busy (rate limited).", code="llm_rate_limited")
        if isinstance(exc, openai.BadRequestError | openai.UnprocessableEntityError):
            if _is_context_overflow(exc):
                return NonRetryableAgentError(
                    "The request is longer than the model's context window. Load the model with a larger "
                    "context (e.g. `lms load <model> --context-length 16384`) or use fewer notes.",
                    code="llm_context",
                )
            return NonRetryableAgentError(
                f"{where.capitalize()} refused the request: {_server_message(exc)}", code="llm_bad_request"
            )
        if isinstance(exc, openai.APIStatusError):
            return AgentError(
                f"{where.capitalize()} had a problem (HTTP {exc.status_code}).",
                code="llm_server_error",
                retryable=exc.status_code >= 500,
            )
        if isinstance(exc, openai.APIError):
            return AgentError(f"{where.capitalize()} sent a broken answer.", code="llm_bad_response")
        return AgentError(f"The model call failed ({type(exc).__name__}).", code="llm_error")


def _reasoning(part: Any) -> bool:
    """Whether a message or stream delta carries reasoning: LM Studio and Ollama send `reasoning_content`
    (or `reasoning`) beside `content`. The SDK keeps unknown fields as extras."""
    return bool(getattr(part, "reasoning_content", None) or getattr(part, "reasoning", None))


def strip_thinking(text: str) -> str:
    """Drop `<think>…</think>` blocks; an unclosed one means the model never got to the answer."""
    text = _THINK.sub("", text)
    if re.match(r"\s*<think>", text, re.I):
        return ""
    return text.strip()


def portable_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """`schema` without keywords strict modes reject, objects closed. Also: is it strict-compatible?"""
    strict = True

    def clean(node: Any) -> Any:
        nonlocal strict
        if isinstance(node, list):
            return [clean(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {k: clean(v) for k, v in node.items() if k not in _UNPORTABLE}
        if "properties" in node:
            out["properties"] = {name: clean(sub) for name, sub in node["properties"].items()}
            out["additionalProperties"] = False
            if set(out.get("required", [])) != set(node["properties"]):
                strict = False  # strict modes need every property required
        return out

    return clean(schema), strict


def _response_format(mode: Structured, wants_json: bool, json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if not wants_json or mode == "none":
        return None
    if mode == "json_schema" and json_schema is not None:
        schema, strict = portable_schema(json_schema)
        name = _SCHEMA_NAME.sub("_", str(json_schema.get("title") or "answer"))[:64] or "answer"
        return {"type": "json_schema", "json_schema": {"name": name, "strict": strict, "schema": schema}}
    return {"type": "json_object"}


def _tool_call(raw: dict[str, Any], index: int) -> ToolCall:
    function = raw.get("function") or {}
    arguments = function.get("arguments") or "{}"
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("arguments are not an object")
    except (ValueError, TypeError):
        parsed = {"_unparsed": str(arguments)}
    return ToolCall(id=str(raw.get("id") or f"call_{index}"), name=str(function.get("name") or ""), arguments=parsed)


def _server_message(exc: BaseException) -> str:
    body = getattr(exc, "body", None)
    message = None
    if isinstance(body, dict):
        error = body.get("error", body)
        message = error.get("message") if isinstance(error, dict) else error
    text = str(message or getattr(exc, "message", "") or type(exc).__name__)
    return text.splitlines()[0][:200] if text else type(exc).__name__


def _is_context_overflow(exc: BaseException) -> bool:
    text = _server_message(exc).lower()
    return any(s in text for s in ("context length", "context window", "maximum context", "n_ctx", "too many tokens"))


def _mentions_missing_model(exc: BaseException) -> bool:
    text = _server_message(exc).lower()
    return "no models loaded" in text or ("model" in text and ("not found" in text or "not loaded" in text))
