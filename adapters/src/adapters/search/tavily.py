"""SearchPort backed by Tavily (https://docs.tavily.com/documentation/api-reference/endpoint/search).

The orchestrator owns retries, so each failure says whether one can help. Spent quota (432 plan
limit, 433 pay-as-you-go limit), a rejected key and a refused request can't be fixed by trying
again; a timeout, a rate limit, a 5xx or a garbled reply might. The key goes in the Authorization
header and never into an error message.
"""

from __future__ import annotations

from typing import Any

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import Source

TAVILY_URL = "https://api.tavily.com/search"
MAX_RESULTS = 20  # Tavily's own limit for max_results


class TavilySearch:
    """Install with `gp-adapters[search]`."""

    def __init__(self, api_key: str, timeout: float = 20.0, *, transport: Any = None):
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport  # an httpx transport, for tests

    async def search(self, query: str, n: int) -> list[Source]:
        import httpx

        payload = {"query": query, "max_results": max(1, min(n, MAX_RESULTS))}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(TAVILY_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AgentError(
                f"The research service didn't answer within {self._timeout:g} s.", code="search_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise AgentError("Couldn't reach the research service.", code="search_unreachable") from exc
        _raise_for_status(response.status_code)
        return _sources(response, n)


def _raise_for_status(code: int) -> None:
    if code < 400:
        return
    if code in (401, 403):
        raise NonRetryableAgentError(
            "The research service rejected its API key — check SEARCH_API_KEY.", code="search_auth"
        )
    if code == 432:
        raise NonRetryableAgentError(
            "The research service's plan limit is used up; retrying won't help until it resets.", code="search_quota"
        )
    if code == 433:
        raise NonRetryableAgentError(
            "The research service's pay-as-you-go limit is reached; retrying won't help until it's raised.",
            code="search_quota",
        )
    if code == 429:
        raise AgentError("The research service is rate-limiting requests.", code="search_rate_limited")
    if code >= 500:
        raise AgentError(f"The research service had a problem ({code}).", code="search_error")
    raise NonRetryableAgentError(f"The research service refused the request ({code}).", code="search_bad_request")


def _sources(response: Any, n: int) -> list[Source]:
    try:
        body = response.json()
    except ValueError:
        body = None
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        raise AgentError("The research service sent a reply that isn't a list of results.", code="search_bad_response")
    sources = [
        Source(title=str(r.get("title") or ""), url=r["url"], snippet=str(r.get("content") or ""))
        for r in results
        if isinstance(r, dict) and isinstance(r.get("url"), str) and r["url"]
    ]
    return sources[:n]
