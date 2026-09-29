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
    openai_base_url: str | None = None
    search_api_key: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    youtube_credentials: dict | None = None
    drive_credentials: dict | None = None
    mailtrap_api_token: str | None = None
    mail_from_email: str | None = None


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

        llm = OpenAILLM(settings.openai_api_key, settings.openai_model, settings.openai_base_url)

    search = FakeSearch()
    if settings.search_api_key:
        from adapters.search.tavily import TavilySearch

        search = TavilySearch(settings.search_api_key)

    image = FakeImage()
    if settings.cloudflare_account_id and settings.cloudflare_api_token:
        from adapters.image.cloudflare import CloudflareImage

        image = CloudflareImage(settings.cloudflare_account_id, settings.cloudflare_api_token)

    from adapters.tts.gtts import GTTS

    email = FakeEmail()
    if settings.mailtrap_api_token and settings.mail_from_email:
        from adapters.email.mailtrap import MailtrapEmail

        email = MailtrapEmail(settings.mailtrap_api_token, settings.mail_from_email)

    publishers = {}
    if settings.google_client_id and settings.google_client_secret:
        from adapters.publish.drive import DrivePublisher
        from adapters.publish.youtube import YouTubePublisher

        if settings.youtube_credentials:
            publishers["youtube"] = YouTubePublisher(
                settings.youtube_credentials, client_id=settings.google_client_id,
                client_secret=settings.google_client_secret, storage_root=settings.storage_root,
            )
        if settings.drive_credentials:
            publishers["drive"] = DrivePublisher(
                settings.drive_credentials, client_id=settings.google_client_id,
                client_secret=settings.google_client_secret, storage_root=settings.storage_root,
            )

    return Ports(
        llm=llm,
        search=search,
        tts=GTTS(),
        image=image,
        storage=storage,
        email=email,
        publishers=publishers,
    )
