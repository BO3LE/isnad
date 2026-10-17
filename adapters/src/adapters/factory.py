"""Build the `Ports` bundle the worker injects into agents.

`FAKE_ADAPTERS=true` runs the entire platform end to end with canned responses —
no API spend, no network. Each real adapter is switched on individually as it lands.
Storage is chosen separately by `STORAGE_BACKEND` (see `build_storage`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from adapters.email.fake import FakeEmail
from adapters.image.fake import FakeImage
from adapters.llm.fake import FakeLLM
from adapters.publish.fake import FakePublisher
from adapters.search.fake import FakeSearch
from adapters.storage.local import LocalStorage
from adapters.tts.fake import FakeTTS
from contracts.errors import NonRetryableAgentError
from contracts.ports import EmailPort, LLMPort, Ports, SearchPort, Source, StoragePort

LLMProvider = Literal["local", "openai", "openrouter", "fake"]
SearchProvider = Literal["tavily", "fake"]
EmailTransport = Literal["gmail", "smtp"]
# Where each provider lives unless LLM_BASE_URL says otherwise. "local" is LLM_LOCAL_BASE_URL:
# LM Studio's default port here, http://host.docker.internal:1234/v1 from inside Docker (compose
# sets that), or Ollama's http://localhost:11434/v1.
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


@dataclass(frozen=True)
class AdapterSettings:
    fake: bool = True
    storage_root: str = "/data/artifacts"
    public_base_url: str = "http://localhost:8000/files"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    search_api_key: str | None = None
    # Search (real mode only). None: "tavily" if SEARCH_API_KEY is set; with no key either, each
    # Researcher step fails saying so — "fake" has to be chosen, it is never fallen back to.
    search_provider: SearchProvider | None = None
    # LLM (real mode only). None: "openai" if OPENAI_API_KEY is set (as before), else "local".
    llm_provider: LLMProvider | None = None
    llm_base_url: str | None = None
    llm_local_base_url: str = "http://localhost:1234/v1"
    llm_model: str | None = None
    llm_api_key: str | None = None
    openrouter_api_key: str | None = None
    llm_structured: Literal["json_schema", "json_object", "none"] = "json_schema"
    llm_timeout_s: float = 300.0
    llm_max_output_tokens: int = 4096
    llm_temperature: float | None = None
    llm_stream: bool = True
    # Where generated files go, independent of FAKE_ADAPTERS: "local" (STORAGE_ROOT, development)
    # or "supabase" (the private bucket STORAGE_BUCKET, production).
    storage_backend: Literal["local", "supabase"] = "local"
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    storage_bucket: str = "artifacts"
    # Email (real mode only). "gmail": through the Google account the step names (D-09). "smtp":
    # through this server's SMTP — Mailpit in development, which catches everything locally.
    email_transport: EmailTransport = "gmail"
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None  # a secret — never log it
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    email_from: str = "ISNAD <isnad@localhost>"


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

    llm = build_llm(settings)
    search = build_search(settings)

    from adapters._google import NoGooglePublisher
    from adapters.tts.gtts import GTTS

    # Publishing — and email with EMAIL_TRANSPORT=gmail — acts as a person's Google account, so there
    # is no process-wide real adapter: the worker swaps these placeholders for
    # `adapters._google.google_ports(credential)` when a node names a connected account (D-09).
    # Without one, the step fails with a readable "needs a Google connection" rather than pretending.
    # With EMAIL_TRANSPORT=smtp, email is this server's SMTP for every step (build_email).
    return Ports(
        llm=llm,
        search=search,
        tts=GTTS(),
        image=FakeImage(),
        storage=storage,
        email=build_email(settings),
        publishers={"youtube": NoGooglePublisher(), "drive": NoGooglePublisher()},
    )


def connection_ports(settings: AdapterSettings) -> frozenset[str]:
    """The `Ports` fields that, on this server, go through the Google account a step names.

    A step's credential field says which port it supplies (`x-port` in its config schema). Publishing
    always acts as the person's account; email does only with EMAIL_TRANSPORT=gmail.
    """
    if settings.fake:
        return frozenset()
    return frozenset({"publishers", "email"} if settings.email_transport == "gmail" else {"publishers"})


class MisconfiguredEmail:
    """Stands in when the email settings can't work: the Email step says why, before anything is sent."""

    def __init__(self, message: str):
        self.message = message

    async def send(self, to: list[str], subject: str, body: str) -> str:
        raise NonRetryableAgentError(self.message, code="email_misconfigured")


def build_email(settings: AdapterSettings) -> EmailPort:
    """The process-wide email port for real mode. With gmail, the worker swaps in the account's port per step."""
    if settings.email_transport == "gmail":
        from adapters._google import NoGoogleEmail

        return NoGoogleEmail()
    if settings.email_transport != "smtp":
        return MisconfiguredEmail(f"EMAIL_TRANSPORT={settings.email_transport!r} isn't one of gmail, smtp.")
    if not settings.smtp_host:
        return MisconfiguredEmail("EMAIL_TRANSPORT=smtp needs SMTP_HOST (mailpit, inside docker compose).")
    if settings.smtp_starttls and settings.smtp_ssl:
        return MisconfiguredEmail("Set SMTP_STARTTLS or SMTP_SSL, not both.")
    from adapters.email.smtp import SmtpConfig, SmtpEmail

    return SmtpEmail(
        SmtpConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.email_from,
            username=settings.smtp_username,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            ssl=settings.smtp_ssl,
        )
    )


class MisconfiguredLLM:
    """Stands in when the LLM settings can't work, so each step says why instead of the worker crashing."""

    def __init__(self, message: str):
        self.message = message

    async def complete(self, prompt: str, **_: Any) -> str:
        raise NonRetryableAgentError(self.message, code="llm_misconfigured")

    async def chat(self, messages: Any, **_: Any) -> Any:
        raise NonRetryableAgentError(self.message, code="llm_misconfigured")


class MisconfiguredSearch:
    """Stands in when real-mode search isn't set up: the Researcher's step says why, at once."""

    def __init__(self, message: str):
        self.message = message

    async def search(self, query: str, n: int) -> list[Source]:
        raise NonRetryableAgentError(self.message, code="search_misconfigured")


def search_provider(settings: AdapterSettings) -> SearchProvider | None:
    if settings.search_provider:
        return settings.search_provider
    return "tavily" if settings.search_api_key else None


def build_search(settings: AdapterSettings) -> SearchPort:
    """The search for real mode. Made-up sources only when SEARCH_PROVIDER=fake says so (F8)."""
    provider = search_provider(settings)
    if provider is None:
        return MisconfiguredSearch(
            "Search isn't set up: set SEARCH_API_KEY for Tavily, or SEARCH_PROVIDER=fake to use made-up sources."
        )
    if provider == "fake":
        return FakeSearch()
    if provider != "tavily":
        return MisconfiguredSearch(f"SEARCH_PROVIDER={provider!r} isn't one of tavily, fake.")
    if not settings.search_api_key:
        return MisconfiguredSearch("SEARCH_PROVIDER=tavily needs SEARCH_API_KEY.")
    try:
        import httpx  # noqa: F401 — the adapter's one dependency
    except ImportError:
        return MisconfiguredSearch("The search adapter isn't installed on this worker: install gp-adapters[search].")
    from adapters.search.tavily import TavilySearch

    return TavilySearch(settings.search_api_key)


def llm_provider(settings: AdapterSettings) -> LLMProvider:
    if settings.llm_provider:
        return settings.llm_provider
    return "openai" if settings.openai_api_key else "local"


def build_llm(settings: AdapterSettings) -> LLMPort:
    """The LLM for real mode. Chosen explicitly — a missing key is an error a step reports, never a fake."""
    provider = llm_provider(settings)
    if provider == "fake":
        return FakeLLM()
    if provider not in ("local", *DEFAULT_BASE_URLS):
        return MisconfiguredLLM(f"LLM_PROVIDER={provider!r} isn't one of local, openai, openrouter, fake.")
    key = settings.llm_api_key or {
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
    }.get(provider)
    if provider != "local" and not key:
        name = "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY"
        return MisconfiguredLLM(f"LLM_PROVIDER={provider} needs {name} (or LLM_API_KEY).")
    model = settings.llm_model or (settings.openai_model if provider == "openai" else None)
    if not model:
        hint = " — the id LM Studio shows (`lms ls`, or GET /v1/models)" if provider == "local" else ""
        return MisconfiguredLLM(f"Set LLM_MODEL to the model to use{hint}.")

    try:
        import openai  # noqa: F401 — the SDK is an extra: gp-adapters[openai]

        from adapters.llm.openai_compatible import LLMConfig, OpenAICompatibleLLM
    except ImportError:
        return MisconfiguredLLM("The LLM adapter isn't installed on this worker: install gp-adapters[openai].")

    return OpenAICompatibleLLM(
        LLMConfig(
            provider=provider,
            base_url=(settings.llm_base_url or DEFAULT_BASE_URLS.get(provider, settings.llm_local_base_url)).rstrip(
                "/"
            ),
            model=model,
            api_key=key,
            structured=settings.llm_structured,
            timeout_s=settings.llm_timeout_s,
            max_output_tokens=settings.llm_max_output_tokens,
            temperature=settings.llm_temperature,
            stream=settings.llm_stream,
        )
    )
