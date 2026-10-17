"""Which search real mode uses (SEARCH_PROVIDER), and that made-up sources are chosen, never fallen back to (F8)."""

from __future__ import annotations

import pytest

from adapters.factory import AdapterSettings, MisconfiguredSearch, build_ports, build_search
from adapters.search.fake import FakeSearch
from adapters.search.tavily import TavilySearch
from contracts.errors import AgentError


def real(**search) -> AdapterSettings:
    return AdapterSettings(fake=False, storage_root="/tmp/gp-test", llm_model="m", **search)


def test_fake_adapters_mode_never_builds_a_real_search(tmp_path):
    settings = AdapterSettings(fake=True, storage_root=str(tmp_path), search_provider="tavily", search_api_key="k")
    assert isinstance(build_ports(settings).search, FakeSearch)


def test_a_key_alone_still_selects_tavily_as_before():
    assert isinstance(build_search(real(search_api_key="tvly-k")), TavilySearch)
    assert isinstance(build_ports(real(search_api_key="tvly-k")).search, TavilySearch)


def test_made_up_sources_only_when_asked_for():
    assert isinstance(build_search(real(search_provider="fake")), FakeSearch)
    # Even with a key: "fake" is what was chosen.
    assert isinstance(build_search(real(search_provider="fake", search_api_key="tvly-k")), FakeSearch)


@pytest.mark.parametrize(
    ("settings", "fragment"),
    [
        ({}, "set SEARCH_API_KEY for Tavily, or SEARCH_PROVIDER=fake"),
        ({"search_provider": "tavily"}, "SEARCH_PROVIDER=tavily needs SEARCH_API_KEY"),
        ({"search_provider": "bing"}, "isn't one of tavily, fake"),
    ],
    ids=["nothing-set", "tavily-without-a-key", "unknown-provider"],
)
async def test_search_that_cant_work_fails_the_step_saying_why(settings, fragment):
    search = build_search(real(**settings))

    assert isinstance(search, MisconfiguredSearch)
    assert fragment in search.message
    with pytest.raises(AgentError) as caught:
        await search.search("solar", 3)
    assert (caught.value.code, caught.value.retryable) == ("search_misconfigured", False)


def test_real_mode_without_search_settings_is_no_longer_silently_fake():
    assert not isinstance(build_ports(real()).search, FakeSearch)
