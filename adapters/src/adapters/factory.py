"""Build the `Ports` bundle the worker injects into agents.

`FAKE_ADAPTERS=true` runs the entire platform end to end with canned responses —
no API spend, no network. Each real adapter is switched on individually as it lands.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.email.fake import FakeEmail
from adapters.image.fake import FakeImage
from adapters.llm.fake import FakeLLM
from adapters.publish.fake import FakePublisher
from adapters.search.fake import FakeSearch
from adapters.storage.local import LocalStorage
from adapters.tts.fake import FakeTTS
from contracts.ports import Ports


@dataclass(frozen=True)
class AdapterSettings:
    fake: bool = True
    storage_root: str = "/data/artifacts"
    public_base_url: str = "http://localhost:8000/files"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    search_api_key: str | None = None


def build_ports(settings: AdapterSettings) -> Ports:
    storage = LocalStorage(settings.storage_root, settings.public_base_url)
    if settings.fake:
        return Ports(
            llm=FakeLLM(),
            search=FakeSearch(),
            tts=FakeTTS(),
            image=FakeImage(),
            storage=storage,
            email=FakeEmail(),
            publishers={"youtube": FakePublisher("youtube"), "drive": FakePublisher("drive")},
        )

    llm = FakeLLM()
    if settings.openai_api_key:
        from adapters.llm.openai import OpenAILLM

        llm = OpenAILLM(settings.openai_api_key, settings.openai_model)

    search = FakeSearch()
    if settings.search_api_key:
        from adapters.search.tavily import TavilySearch

        search = TavilySearch(settings.search_api_key)

    from adapters._google import NoGoogleEmail, NoGooglePublisher
    from adapters.tts.gtts import GTTS

    # Publishing and email act as a person's Google account, so there is no process-wide real
    # adapter: the worker swaps these placeholders for `adapters._google.google_ports(credential)`
    # when a node names a connected account (D-09). Without one, the step fails with a readable
    # "needs a Google connection" rather than pretending to publish.
    return Ports(
        llm=llm,
        search=search,
        tts=GTTS(),
        image=FakeImage(),
        storage=storage,
        email=NoGoogleEmail(),
        publishers={"youtube": NoGooglePublisher(), "drive": NoGooglePublisher()},
    )
