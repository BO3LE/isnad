"""TavilySearch against a stand-in for Tavily's API (httpx MockTransport): no network, no credit spent.

What each failure tells the orchestrator — retry or stop — and that the key travels only in the
Authorization header, never in the body or a message a person sees.
"""

from __future__ import annotations

import json

import httpx
import pytest

from adapters.search.tavily import TAVILY_URL, TavilySearch
from contracts.errors import AgentError

KEY = "tvly-CANARY-key-0123456789"
RESULTS = {
    "query": "solar",
    "results": [
        {"title": "Solar in KSA", "url": "https://example.org/a", "content": "Irradiance is high.", "score": 0.9},
        {"title": "Grid", "url": "https://example.org/b", "content": "Storage matters.", "score": 0.8},
    ],
    "images": [],
    "answer": None,
    "response_time": 0.5,
}


def _tavily(handler) -> TavilySearch:
    return TavilySearch(KEY, timeout=5, transport=httpx.MockTransport(handler))


def _answer(status: int, body: object = None, *, raw: bytes | None = None):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body if body is not None else {"detail": {"error": "x"}})

    handler.requests = requests
    return handler


async def test_results_become_sources_and_the_key_goes_only_in_the_header():
    handler = _answer(200, RESULTS)

    sources = await _tavily(handler).search("solar", 5)

    assert [(s.title, s.url, s.snippet) for s in sources] == [
        ("Solar in KSA", "https://example.org/a", "Irradiance is high."),
        ("Grid", "https://example.org/b", "Storage matters."),
    ]
    (request,) = handler.requests
    assert (request.method, str(request.url)) == ("POST", TAVILY_URL)
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body == {"query": "solar", "max_results": 5}
    assert KEY not in request.content.decode()


async def test_max_results_stays_within_tavilys_limit_and_the_answer_is_cut_to_n():
    handler = _answer(200, RESULTS)
    await _tavily(handler).search("solar", 50)
    assert json.loads(handler.requests[0].content)["max_results"] == 20

    assert len(await _tavily(_answer(200, RESULTS)).search("solar", 1)) == 1


async def test_results_without_a_url_are_left_out():
    body = dict(
        RESULTS, results=[{"title": "no url"}, "not an object", {"url": "", "title": "empty"}, RESULTS["results"][0]]
    )
    sources = await _tavily(_answer(200, body)).search("solar", 5)
    assert [s.url for s in sources] == ["https://example.org/a"]


@pytest.mark.parametrize(
    ("status", "code", "retryable", "fragment"),
    [
        (401, "search_auth", False, "rejected its API key"),
        (403, "search_auth", False, "rejected its API key"),
        (432, "search_quota", False, "plan limit is used up"),
        (433, "search_quota", False, "pay-as-you-go limit"),
        (400, "search_bad_request", False, "refused the request (400)"),
        (422, "search_bad_request", False, "refused the request (422)"),
        (429, "search_rate_limited", True, "rate-limiting"),
        (500, "search_error", True, "had a problem (500)"),
        (503, "search_error", True, "had a problem (503)"),
    ],
)
async def test_each_error_says_whether_a_retry_can_help(status, code, retryable, fragment):
    with pytest.raises(AgentError) as caught:
        await _tavily(_answer(status)).search("solar", 5)

    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert fragment in caught.value.message
    assert KEY not in caught.value.message


async def test_a_timeout_is_retryable_and_says_how_long_it_waited():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AgentError) as caught:
        await _tavily(handler).search("solar", 5)

    assert (caught.value.code, caught.value.retryable) == ("search_timeout", True)
    assert "within 5 s" in caught.value.message


async def test_an_unreachable_service_is_retryable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AgentError) as caught:
        await _tavily(handler).search("solar", 5)

    assert (caught.value.code, caught.value.retryable) == ("search_unreachable", True)


@pytest.mark.parametrize(
    "reply",
    [b"<html>Bad gateway</html>", b'{"results": "none"}', b"[1, 2]"],
    ids=["not-json", "results-not-a-list", "not-an-object"],
)
async def test_a_garbled_reply_is_a_readable_retryable_error_not_a_crash(reply):
    with pytest.raises(AgentError) as caught:
        await _tavily(_answer(200, raw=reply)).search("solar", 5)

    assert (caught.value.code, caught.value.retryable) == ("search_bad_response", True)
