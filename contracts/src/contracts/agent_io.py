"""Input, output and configuration models for each agent.

How inputs are built (worker): the outputs of all upstream agents are merged in
execution order, then the node's saved configuration is applied on top, and the
result is validated against the agent's input model. Field aliases below let an
agent accept the name an upstream agent uses (e.g. Video reads Writer's
`article_md` as its `script`).

`*Config` models are what the user fills in on the canvas. Their JSON Schema is
published through `/agents/catalog` and builds the configuration drawer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from contracts.ports import Source

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- Researcher
class ResearchConfig(_Config):
    topic: str = Field(min_length=3, max_length=300, title="Topic", description="What should the Researcher look into?")
    num_sources: int = Field(5, ge=1, le=10, title="Number of sources", json_schema_extra={"x-unit": "sources"})


class ResearchInput(_In):
    topic: str = Field(min_length=3, max_length=300)
    num_sources: int = Field(5, ge=1, le=10)


class ResearchOutput(_Out):
    notes: list[str]
    sources: list[Source]


# ---------------------------------------------------------------- Writer
Length = Literal["short", "medium", "long"]
Style = Literal["informative", "persuasive", "conversational", "academic"]
Format = Literal["blog_post", "article", "video_script"]


class WriteConfig(_Config):
    length: Length = Field("medium", title="Length")
    style: Style = Field("informative", title="Style")
    format: Format = Field("blog_post", title="Format")


class WriteInput(_In):
    notes: list[str] = Field(min_length=1)
    sources: list[Source] = Field(default_factory=list)
    length: Length = "medium"
    style: Style = "informative"
    format: Format = "blog_post"


class WriteOutput(_Out):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    article_md: str = Field(min_length=1)


# ---------------------------------------------------------------- Image
class ImageConfig(_Config):
    prompt: str | None = Field(
        None, title="What should the image show?", description="Leave empty to use the article title."
    )
    count: int = Field(1, ge=1, le=4, title="Number of images")
    aspect: Literal["landscape", "square"] = Field("landscape", title="Shape")


class ImageInput(_In):
    prompt: str = Field(min_length=1, validation_alias=AliasChoices("prompt", "title"))
    count: int = Field(1, ge=1, le=4)
    aspect: Literal["landscape", "square"] = "landscape"


class ImageOutput(_Out):
    image_paths: list[str] = Field(min_length=1)


# ---------------------------------------------------------------- Video
class VideoConfig(_Config):
    voice: str = Field("en", title="Narration voice", description="Language code for narration, e.g. en, en-uk.")
    resolution: Literal["720p", "1080p"] = Field("720p", title="Resolution")


class VideoInput(_In):
    script: str = Field(min_length=1, validation_alias=AliasChoices("script", "article_md"))
    title: str = ""
    voice: str = "en"
    resolution: Literal["720p", "1080p"] = "720p"


class VideoOutput(_Out):
    video_path: str
    duration_seconds: float = Field(ge=0)


# ---------------------------------------------------------------- Publisher
class PublishConfig(_Config):
    platform: Literal["youtube", "drive"] = Field("youtube", title="Publish to")
    credential_id: str | None = Field(
        None, title="Google account", json_schema_extra={"x-widget": "credential", "x-provider": "google"}
    )
    title: str | None = Field(None, max_length=100, title="Title", description="Leave empty to use the article title.")
    tags: list[str] = Field(default_factory=list, title="Tags")
    privacy: Literal["unlisted", "private", "public"] = Field("unlisted", title="Visibility")


class PublishInput(_In):
    file_path: str = Field(validation_alias=AliasChoices("file_path", "video_path"))
    platform: Literal["youtube", "drive"] = "youtube"
    credential_id: str | None = None
    title: str = Field(min_length=1, max_length=100)
    description: str = Field("", validation_alias=AliasChoices("description", "summary"))
    tags: list[str] = Field(default_factory=list)
    privacy: Literal["unlisted", "private", "public"] = "unlisted"


class PublishOutput(_Out):
    platform: Literal["youtube", "drive"]
    remote_url: str
    platform_id: str


# ---------------------------------------------------------------- Email
class EmailConfig(_Config):
    recipients: list[str] = Field(min_length=1, title="To")
    subject: str | None = Field(
        None, max_length=150, title="Subject", description="Leave empty to use the article title."
    )
    body: str | None = Field(None, title="Message")

    @field_validator("recipients")
    @classmethod
    def _emails(cls, value: list[str]) -> list[str]:
        return _check_emails(value)


class EmailInput(_In):
    recipients: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=150, validation_alias=AliasChoices("subject", "title"))
    body: str = Field("", validation_alias=AliasChoices("body", "summary"))
    links: list[str] = Field(default_factory=list, validation_alias=AliasChoices("links", "remote_url"))

    @field_validator("recipients")
    @classmethod
    def _emails(cls, value: list[str]) -> list[str]:
        return _check_emails(value)

    @field_validator("links", mode="before")
    @classmethod
    def _one_link(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


class EmailOutput(_Out):
    message_id: str
    sent_at: datetime
    recipients: list[str]


def _check_emails(value: list[str]) -> list[str]:
    import re

    bad = [v for v in value if not re.match(EMAIL_PATTERN, v)]
    if bad:
        raise ValueError(f"not a valid email address: {', '.join(bad)}")
    return value
