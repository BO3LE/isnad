"""Adapter interfaces. Agents talk to the outside world only through these ports.

Port shapes are owned by Mohammed; implementations live in `adapters/` (Zain).
Every port has a fake in `adapters/*/fake.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Source(BaseModel):
    title: str
    url: str
    snippet: str = ""


class PublishMetadata(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    privacy: Literal["unlisted", "private", "public"] = "unlisted"


class PublishResult(BaseModel):
    remote_url: str
    platform_id: str


@runtime_checkable
class LLMPort(Protocol):
    async def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str: ...


@runtime_checkable
class SearchPort(Protocol):
    async def search(self, query: str, n: int) -> list[Source]: ...


@runtime_checkable
class TTSPort(Protocol):
    async def speak(self, text: str, *, voice: str) -> bytes:
        """Return encoded audio (WAV or MP3) for `text`."""
        ...


@runtime_checkable
class ImagePort(Protocol):
    """Added in M3 for the Image agent — provider still to be chosen (risk R1)."""

    async def generate(self, prompt: str, *, aspect: Literal["landscape", "square"]) -> bytes:
        """Return PNG bytes."""
        ...


@runtime_checkable
class PublishPort(Protocol):
    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult: ...


@runtime_checkable
class EmailPort(Protocol):
    async def send(self, to: list[str], subject: str, body: str) -> str:
        """Send an email and return the provider message id."""
        ...


@runtime_checkable
class StoragePort(Protocol):
    async def put(self, path: str, data: bytes, content_type: str) -> str:
        """Store bytes and return the storage path."""
        ...

    async def get(self, path: str) -> bytes: ...

    async def signed_url(self, path: str, expires_in: int = 3600) -> str: ...


@dataclass(frozen=True)
class Ports:
    """Everything an agent may use. Injected by the worker; agents never build their own."""

    llm: LLMPort
    search: SearchPort
    tts: TTSPort
    image: ImagePort
    storage: StoragePort
    email: EmailPort
    publishers: Mapping[str, PublishPort] = field(default_factory=dict)
