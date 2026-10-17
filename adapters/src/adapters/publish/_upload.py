"""Google's resumable upload, shared by the YouTube and Drive publishers.

Two requests: a POST with the metadata opens an upload session (its URL comes back in `Location`),
then one PUT sends the bytes. Nothing is published until the PUT completes, so:

- A failure while opening the session is safe to retry: no video or file exists yet.
- Once the bytes may have reached Google, a lost answer is *not* retried blindly — that could upload
  the same video twice. The session is asked how far it got (`Content-Range: bytes */N`): finished
  → the result is used; incomplete → nothing was published, so a retry is safe; no answer → the
  step fails without a retry and says to check the account first.

https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
https://developers.google.com/workspace/drive/api/guides/manage-uploads#resumable
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import httpx

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import StoragePort

# Per network operation, not for the whole upload: a large file keeps writing for as long as it
# needs; a stalled connection is noticed within this. The orchestrator's STEP_TIMEOUT_S bounds the rest.
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass(frozen=True)
class Service:
    """What differs between YouTube and Drive."""

    name: str  # as a person reads it: "YouTube", "Google Drive"
    code: str  # error-code prefix: "youtube", "drive"
    check_where: str  # where to look before running again: "YouTube Studio"
    error: Callable[[httpx.Response], AgentError]  # a refusal Google explained


def unreachable(service: Service) -> AgentError:
    # DESIGN-SYSTEM §23.5: "Couldn't reach {service}. It may be a temporary network problem."
    return AgentError(
        f"Couldn't reach {service.name}. It may be a temporary network problem.", code=f"{service.code}_unreachable"
    )


def ambiguous(service: Service) -> NonRetryableAgentError:
    return NonRetryableAgentError(
        f"{service.name} didn't confirm the upload, so it may have finished. Check {service.check_where} "
        "before running again.",
        code=f"{service.code}_ambiguous",
    )


async def read_file(storage: StoragePort, storage_path: str) -> tuple[bytes, str]:
    """The file to publish, from storage (never from a local path), and its media type."""
    try:
        data = await storage.get(storage_path)
    except AgentError:
        raise
    except FileNotFoundError as exc:
        raise NonRetryableAgentError(
            "The file to publish is no longer in storage. Run the steps before Publisher again.",
            code="publish_file_missing",
        ) from exc
    except ValueError as exc:  # a path storage refuses (outside its root)
        raise NonRetryableAgentError("The file to publish has an invalid path.", code="publish_file_path") from exc
    except OSError as exc:
        raise AgentError("Couldn't read the file to publish from storage.", code="publish_file_unreadable") from exc
    if not data:
        raise NonRetryableAgentError("The file to publish is empty.", code="publish_file_empty")
    content_type = mimetypes.guess_type(PurePosixPath(storage_path).name)[0] or "application/octet-stream"
    return data, content_type


async def upload(
    service: Service,
    *,
    start_url: str,
    metadata: Mapping[str, Any],
    data: bytes,
    content_type: str,
    token: str,
    http_timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Upload `data` with `metadata`; return the resource Google created (a video, a file)."""
    auth = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=http_timeout, transport=transport) as client:
        # 1. Open the session. Nothing exists on Google's side until the bytes are in.
        try:
            opened = await client.post(
                start_url,
                json=dict(metadata),
                headers=auth | {"X-Upload-Content-Type": content_type, "X-Upload-Content-Length": str(len(data))},
            )
        except httpx.HTTPError as exc:
            raise unreachable(service) from exc
        if opened.status_code != 200:
            raise _refusal(service, opened)
        session = opened.headers.get("location")
        if not session:
            raise AgentError(f"{service.name} didn't open an upload.", code=f"{service.code}_no_session")

        # 2. Send the bytes.
        try:
            sent = await client.put(session, content=data, headers=auth | {"Content-Type": content_type})
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise unreachable(service) from exc  # never left this machine
        except httpx.HTTPError:
            return await _finished_or_raise(client, service, session, auth, len(data))
        if sent.status_code in (200, 201):
            return _created(service, sent)
        if sent.status_code >= 500 or sent.status_code == 308:
            return await _finished_or_raise(client, service, session, auth, len(data))
        raise _refusal(service, sent)  # refused outright: nothing was created


async def _finished_or_raise(
    client: httpx.AsyncClient, service: Service, session: str, auth: dict[str, str], size: int
) -> dict[str, Any]:
    """The answer to the PUT was lost: ask the session whether the upload completed."""
    try:
        status = await client.put(session, headers=auth | {"Content-Range": f"bytes */{size}"})
    except httpx.HTTPError as exc:
        raise ambiguous(service) from exc
    if status.status_code in (200, 201):
        return _created(service, status)
    if status.status_code in (308, 404, 410):
        # Incomplete (308), or the session is gone without finishing (404/410): nothing was published.
        raise AgentError(f"The upload to {service.name} was interrupted.", code=f"{service.code}_interrupted")
    raise ambiguous(service)


def _created(service: Service, response: httpx.Response) -> dict[str, Any]:
    body = json_body(response)
    if not isinstance(body.get("id"), str) or not body["id"]:
        raise ambiguous(service)  # finished, but we can't say what was created
    return body


def _refusal(service: Service, response: httpx.Response) -> AgentError:
    if response.status_code >= 500:
        # Opening the session: nothing exists yet. Google asks clients to retry 5xx.
        return AgentError(
            f"{service.name} had a problem (HTTP {response.status_code}).", code=f"{service.code}_unavailable"
        )
    return service.error(response)


def json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def reasons(response: httpx.Response) -> set[str]:
    error = json_body(response).get("error")
    if not isinstance(error, dict):
        return set()
    return {e.get("reason") for e in error.get("errors") or [] if isinstance(e, dict) and e.get("reason")}


def said(response: httpx.Response) -> str:
    """Google's own explanation, short, for the step's log."""
    error = json_body(response).get("error")
    message = str(error.get("message") or "")[:200] if isinstance(error, dict) else ""
    return f": {message}" if message else ""
