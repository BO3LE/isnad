"""SEARCH_* environment → the Researcher's search, and the startup lines for search and images."""

from __future__ import annotations

import pytest

from adapters.factory import MisconfiguredSearch, build_search
from adapters.search.fake import FakeSearch
from adapters.search.tavily import TavilySearch
from worker import celery_app
from worker.settings import WorkerSettings, adapter_settings

KEY = "tvly-CANARY-key-0123456789"


def _settings(monkeypatch, **env) -> WorkerSettings:
    for name in ("SEARCH_PROVIDER", "SEARCH_API_KEY", "FAKE_ADAPTERS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return WorkerSettings(_env_file=None)


def test_the_environment_selects_the_search(monkeypatch):
    chosen = _settings(monkeypatch, FAKE_ADAPTERS="false", SEARCH_PROVIDER="fake")
    assert isinstance(build_search(adapter_settings(chosen)), FakeSearch)

    keyed = _settings(monkeypatch, FAKE_ADAPTERS="false", SEARCH_API_KEY=KEY)
    assert isinstance(build_search(adapter_settings(keyed)), TavilySearch)


def test_empty_variables_count_as_unset(monkeypatch):
    # As .env.example ships them: `SEARCH_PROVIDER=` and `SEARCH_API_KEY=`.
    settings = _settings(monkeypatch, FAKE_ADAPTERS="false", SEARCH_PROVIDER="", SEARCH_API_KEY="")

    assert settings.search_provider is None and settings.search_api_key is None
    assert isinstance(build_search(adapter_settings(settings)), MisconfiguredSearch)


@pytest.mark.parametrize(
    ("env", "search_line", "image_line"),
    [
        ({"FAKE_ADAPTERS": "true"}, "Search: fake (FAKE_ADAPTERS=true)", "Image: fake (FAKE_ADAPTERS=true)"),
        (
            {"FAKE_ADAPTERS": "false"},
            "Search: not usable — Search isn't set up",
            "Image: fake — there is no real image adapter yet",
        ),
        (
            {"FAKE_ADAPTERS": "false", "SEARCH_PROVIDER": "fake"},
            "Search: fake (SEARCH_PROVIDER=fake) — the Researcher's sources are made up",
            "Image: fake — there is no real image adapter yet",
        ),
        (
            {"FAKE_ADAPTERS": "false", "SEARCH_API_KEY": KEY},
            "Search: tavily",
            "Image: fake — there is no real image adapter yet",
        ),
    ],
    ids=["fake-mode", "nothing-set", "chosen-fake", "tavily"],
)
def test_the_startup_lines(monkeypatch, env, search_line, image_line):
    monkeypatch.setattr(celery_app, "settings", _settings(monkeypatch, **env))

    search, image = celery_app.check_search(), celery_app.check_image()

    assert search.startswith(search_line)
    assert image.startswith(image_line)
    assert KEY not in search
