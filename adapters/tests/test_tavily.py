import asyncio

import httpx
import pytest

from adapters.search.tavily import TAVILY_URL, TavilySearch


def test_tavily_search_uses_bearer_auth_and_maps_results(monkeypatch):
    captured: dict[str, object] = {}

    async def post(self, url, *, json, headers):
        captured.update(url=url, json=json, headers=headers)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Example", "url": "https://example.com", "content": "A useful source."},
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    sources = asyncio.run(TavilySearch("tvly-test").search("agent research", 3))

    assert captured == {
        "url": TAVILY_URL,
        "json": {"query": "agent research", "max_results": 3, "search_depth": "basic"},
        "headers": {"Authorization": "Bearer tvly-test"},
    }
    assert [(source.title, source.url, source.snippet) for source in sources] == [
        ("Example", "https://example.com", "A useful source.")
    ]


@pytest.mark.parametrize("status_code, error_type", [(401, "NonRetryableAgentError"), (429, "AgentError")])
def test_tavily_search_classifies_service_errors(monkeypatch, status_code, error_type):
    async def post(self, url, *, json, headers):
        return httpx.Response(status_code)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(TavilySearch("tvly-test").search("agent research", 3))

    assert type(exc_info.value).__name__ == error_type
