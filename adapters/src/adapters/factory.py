"""Build the `Ports` bundle the worker injects into agents.

`FAKE_ADAPTERS=true` runs the entire platform end to end with canned responses —
no API spend, no network. Each real adapter is switched on individually as it lands.
Storage is chosen separately by `STORAGE_BACKEND` (see `build_storage`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from adapters._google import NoGoogleEmail, NoGooglePublisher
from adapters.email.fake import FakeEmail
from adapters.image.fake import FakeImage
from adapters.llm.fake import FakeLLM
from adapters.publish.fake import FakePublisher
from adapters.search.fake import FakeSearch
from adapters.storage.local import LocalStorage
from adapters.tts.fake import FakeTTS
from contracts.ports import Ports, StoragePort


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
    mailtrap_api_token: str | None = None
    mail_from_email: str | None = None
    # Where generated files go, independent of FAKE_ADAPTERS: "local" (STORAGE_ROOT, development)
    # or "supabase" (the private bucket STORAGE_BUCKET, production).
    storage_backend: Literal["local", "supabase"] = "local"
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    storage_bucket: str = "artifacts"


def build_storage(settings: AdapterSettings) -> StoragePort:
    """The storage every run writes to. Misconfigured Supabase storage fails loudly rather than
    quietly writing files to a local disk the production API cannot serve."""
    if settings.storage_backend == "supabase":
        if not settings.supabase_url or not settings.supabase_service_key:
            raise ValueError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        from adapters.storage.supabase import SupabaseStorage

        return SupabaseStorage(settings.supabase_url, settings.supabase_service_key, settings.storage_bucket)
    if settings.storage_backend != "local":
        raise ValueError(f"unknown STORAGE_BACKEND: {settings.storage_backend!r} (use 'local' or 'supabase')")
    return LocalStorage(settings.storage_root, settings.public_base_url)


def build_ports(settings: AdapterSettings) -> Ports:
    storage = build_storage(settings)
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

    # Email requires an explicit configured service; otherwise fail clearly instead of simulating delivery.
    email = NoGoogleEmail()
    if settings.mailtrap_api_token and settings.mail_from_email:
        from adapters.email.mailtrap import MailtrapEmail

        email = MailtrapEmail(settings.mailtrap_api_token, settings.mail_from_email)

    # Publishing and email act as a person's Google account, so there is no process-wide real
    # adapter: the worker swaps these placeholders for `adapters._google.google_ports(credential)`
    # when a node names a connected account (D-09). Without one, the step fails with a readable
    # "needs a Google connection" rather than pretending to publish.
    return Ports(
        llm=llm,
        search=search,
        tts=GTTS(),
        image=image,
        storage=storage,
        email=email,
        publishers={"youtube": NoGooglePublisher(), "drive": NoGooglePublisher()},
    )
