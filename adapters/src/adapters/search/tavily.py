from __future__ import annotations

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import Source

TAVILY_URL = "https://api.tavily.com/search"


class TavilySearch:
    """SearchPort backed by Tavily. Install with `gp-adapters[search]`."""

    def __init__(self, api_key: str, timeout: float = 20.0):
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, n: int) -> list[Source]:
        import httpx

        payload = {"api_key": self._api_key, "query": query, "max_results": n}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(TAVILY_URL, json=payload)
        except httpx.HTTPError as exc:
            raise AgentError("Couldn't reach the research service.", code="search_unreachable") from exc
        if response.status_code in (401, 403):
            raise NonRetryableAgentError("The research service isn't set up correctly.", code="search_auth")
        if response.status_code >= 400:
            raise AgentError(f"The research service returned an error ({response.status_code}).", code="search_error")
        results = response.json().get("results", [])
        return [
            Source(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", "")) for r in results[:n]
        ]
