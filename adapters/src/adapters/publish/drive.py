"""PublishPort for Google Drive: `files.create` as the Google account the step names (D-09).

`credentials_json` is a resolved, fresh credential (shape in `adapters._google`), built per node by
the worker from the connection the step names — never read from env or the graph. The file is read
through StoragePort, never from a local path. It stays private to that account: nothing is shared
(the step's Visibility is YouTube's), and the link returned opens it for the account's owner.

Retries follow `adapters.publish._upload`: safe until the bytes may have reached Drive, after that
only when Drive says the upload didn't finish — so a retry can't leave two copies.
Errors: https://developers.google.com/workspace/drive/api/guides/handle-errors
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

import httpx

from adapters._google import ExpiredCredentialError
from adapters.publish import _upload
from adapters.publish._upload import reasons, said
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import PublishMetadata, PublishResult, StoragePort

UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,webViewLink"
# drive.file (what the connect flow asks for) reaches only files Isnad created; drive reaches all.
UPLOAD_SCOPES = frozenset({"https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"})
NO_SCOPE_MESSAGE = (
    "This Google connection can't save to Google Drive. In the step's settings choose a connection that lists "
    "Drive, or connect Drive and Gmail in Settings → Connections."
)
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class DrivePublisher:
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
            raise NonRetryableAgentError(NO_SCOPE_MESSAGE, code="drive_scope")
        data, content_type = await _upload.read_file(self._storage, storage_path)
        created = await _upload.upload(
            SERVICE,
            start_url=UPLOAD_URL,
            metadata=file_metadata(storage_path, meta, content_type),
            data=data,
            content_type=content_type,
            token=self._credentials_json["token"],
            http_timeout=self._timeout,
            transport=self._transport,
        )
        link = created.get("webViewLink") or f"https://drive.google.com/file/d/{created['id']}/view"
        return PublishResult(remote_url=link, platform_id=created["id"])


def file_metadata(storage_path: str, meta: PublishMetadata, content_type: str) -> dict[str, Any]:
    """The file's name is the step's title plus the stored file's extension: "Solar in KSA.mp4"."""
    suffix = PurePosixPath(storage_path).suffix
    stem = " ".join(_UNSAFE_NAME.sub(" ", meta.title).split())[:120] or PurePosixPath(storage_path).stem
    return {"name": stem + suffix, "description": meta.description[:4000], "mimeType": content_type}


def _error(response: httpx.Response) -> AgentError:
    code, why, detail = response.status_code, reasons(response), said(response)
    if code == 401:
        return ExpiredCredentialError()
    if "storageQuotaExceeded" in why:
        # DESIGN-SYSTEM §23.5.
        return NonRetryableAgentError("The Google Drive account is full.", code="drive_full")
    if code == 429 or why & {"rateLimitExceeded", "userRateLimitExceeded"}:
        return AgentError("Google Drive is limiting how fast this account can upload.", code="drive_rate_limited")
    if why & {"dailyLimitExceeded", "quotaExceeded"}:
        return NonRetryableAgentError(
            "Google Drive's daily limit for this project has been reached. Try again tomorrow.", code="drive_quota"
        )
    if code == 403 and (why & {"insufficientPermissions", "insufficientFilePermissions"} or "scope" in detail.lower()):
        return NonRetryableAgentError(NO_SCOPE_MESSAGE, code="drive_scope")
    if code == 400:
        return NonRetryableAgentError(f"Google Drive refused the file's details{detail}.", code="drive_rejected")
    return NonRetryableAgentError(f"Google Drive refused the upload ({code}){detail}.", code="drive_refused")


SERVICE = _upload.Service(name="Google Drive", code="drive", check_where="the account's Google Drive", error=_error)
