"""PublishPort for YouTube: `videos.insert` as the Google account the step names (D-09).

`credentials_json` is a resolved, fresh credential (shape in `adapters._google`), built per node by
the worker from the connection the step names — never read from env or the graph. The video is read
through StoragePort, never from a local path. Unlisted unless the step says otherwise (PublishConfig).

Retries follow `adapters.publish._upload`: safe until the bytes may have reached YouTube, after
that only when YouTube says the upload didn't finish — a video can't be un-uploaded by a retry.
Errors: https://developers.google.com/youtube/v3/docs/videos/insert#errors
"""

from __future__ import annotations

from typing import Any

import httpx

from adapters._google import ExpiredCredentialError
from adapters.publish import _upload
from adapters.publish._upload import reasons, said
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import PublishMetadata, PublishResult, StoragePort

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
# Any of these lets videos.insert work; the connect flow asks for youtube.upload.
UPLOAD_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    }
)
CATEGORY_PEOPLE_AND_BLOGS = "22"
NO_SCOPE_MESSAGE = (
    "This Google connection isn't allowed to upload to YouTube. Reconnect Google in Settings → Connections "
    "and leave YouTube ticked."
)
# YouTube's limits on a video's details; it refuses `<` and `>` in the title and description.
TITLE_MAX, DESCRIPTION_MAX_BYTES, TAGS_MAX_CHARS = 100, 5000, 500


class YouTubePublisher:
    def __init__(
        self,
        credentials_json: dict,
        storage: StoragePort,
        *,
        timeout: httpx.Timeout = _upload.DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,  # for tests
    ):
        self._credentials_json = credentials_json
        self._storage = storage
        self._timeout = timeout
        self._transport = transport

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        if not set(self._credentials_json.get("scopes") or []) & UPLOAD_SCOPES:
            raise NonRetryableAgentError(NO_SCOPE_MESSAGE, code="youtube_scope")
        data, content_type = await _upload.read_file(self._storage, storage_path)
        video = await _upload.upload(
            SERVICE,
            start_url=UPLOAD_URL,
            metadata=video_metadata(meta),
            data=data,
            content_type=content_type if content_type.startswith("video/") else "video/*",
            token=self._credentials_json["token"],
            http_timeout=self._timeout,
            transport=self._transport,
        )
        return PublishResult(remote_url=f"https://youtu.be/{video['id']}", platform_id=video["id"])


def video_metadata(meta: PublishMetadata) -> dict[str, Any]:
    """The snippet and status YouTube accepts: within its limits, without the characters it refuses."""
    title = _clean(meta.title)[:TITLE_MAX].strip() or "Untitled"
    description = _clean(meta.description).encode()[:DESCRIPTION_MAX_BYTES].decode(errors="ignore")
    tags: list[str] = []
    for tag in (_clean(t).strip() for t in meta.tags):
        if tag and len(",".join([*tags, tag])) <= TAGS_MAX_CHARS:
            tags.append(tag)
    return {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": CATEGORY_PEOPLE_AND_BLOGS},
        "status": {"privacyStatus": meta.privacy, "selfDeclaredMadeForKids": False},
    }


def _clean(text: str) -> str:
    return text.replace("<", "").replace(">", "")


def _error(response: httpx.Response) -> AgentError:
    code, why, detail = response.status_code, reasons(response), said(response)
    if "youtubeSignupRequired" in why:
        return NonRetryableAgentError(
            "This Google account has no YouTube channel yet. Create one at youtube.com, then run again.",
            code="youtube_no_channel",
        )
    if code == 401:
        return ExpiredCredentialError()
    if "quotaExceeded" in why:
        # DESIGN-SYSTEM §23.5.
        return NonRetryableAgentError(
            "YouTube's daily upload limit for this project has been reached. Try again tomorrow.", code="youtube_quota"
        )
    if "uploadLimitExceeded" in why:
        return NonRetryableAgentError(
            "This YouTube channel has uploaded as many videos as YouTube allows for now. Try again tomorrow.",
            code="youtube_upload_limit",
        )
    if code == 413:
        return NonRetryableAgentError("YouTube rejected the file because it's too large.", code="youtube_too_large")
    if code == 429 or why & {"rateLimitExceeded", "userRateLimitExceeded"}:
        return AgentError("YouTube is limiting how fast this account can upload.", code="youtube_rate_limited")
    if code == 403 and (why & {"insufficientPermissions", "forbidden"} or "scope" in detail.lower()):
        return NonRetryableAgentError(NO_SCOPE_MESSAGE, code="youtube_scope")
    if code == 400:
        return NonRetryableAgentError(f"YouTube refused the video's details{detail}.", code="youtube_rejected")
    return NonRetryableAgentError(f"YouTube refused the upload ({code}){detail}.", code="youtube_refused")


SERVICE = _upload.Service(name="YouTube", code="youtube", check_where="YouTube Studio", error=_error)
