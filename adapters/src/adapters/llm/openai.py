from __future__ import annotations

from contracts.errors import AgentError, NonRetryableAgentError


class OpenAILLM:
    """LLMPort backed by the OpenAI Chat Completions API. Install with `gp-adapters[openai]`."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        import openai

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"} if json_mode else openai.NOT_GIVEN,
            )
        except openai.AuthenticationError as exc:
            raise NonRetryableAgentError("The writing service isn't set up correctly.", code="llm_auth") from exc
        except openai.RateLimitError as exc:
            raise AgentError("The writing service is busy.", code="llm_rate_limited") from exc
        except openai.APIConnectionError as exc:
            raise AgentError("Couldn't reach the writing service.", code="llm_unreachable") from exc
        return response.choices[0].message.content or ""
