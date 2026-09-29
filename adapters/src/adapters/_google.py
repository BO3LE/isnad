"""Shared Google plumbing for the YouTube, Drive and Gmail adapters (D-09).

What the adapters receive is a *resolved* credential — the worker loaded the row the node's
`credential_id` points at, decrypted it and refreshed the access token if needed — in the shape
`google.oauth2.credentials.Credentials.from_authorized_user_info()` accepts:

    {"token": access token, "refresh_token": ..., "token_uri": ..., "client_id": ...,
     "client_secret": ..., "scopes": [...], "expiry": ISO-8601 UTC}

Nothing here reads the database; nothing here is ever given a workflow graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import EmailPort, PublishMetadata, PublishPort, PublishResult

TOKEN_URI = "https://oauth2.googleapis.com/token"

# The messages a person reads (DESIGN-SYSTEM §23.5). The frontend matches on `code` once error codes
# reach the API; until then the message itself is what the log viewer shows.
EXPIRED_MESSAGE = "Your Google connection has expired or was removed. Reconnect Google, then run again."
MISSING_MESSAGE = "This step needs a Google connection. Connect Google in Settings → Connections."
MISCONFIGURED_MESSAGE = "Google connections aren't set up on this server yet. Ask the administrator."


class ExpiredCredentialError(NonRetryableAgentError):
    """Google answered `invalid_grant`: the refresh token was revoked or has expired."""

    def __init__(self, message: str = EXPIRED_MESSAGE):
        super().__init__(message, code="expired_credential")


class MissingCredentialError(NonRetryableAgentError):
    def __init__(self, message: str = MISSING_MESSAGE):
        super().__init__(message, code="missing_credential")


async def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    token_uri: str = TOKEN_URI,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token.

    Returns Google's JSON (`access_token`, `expires_in`, `scope`, `token_type`, and sometimes a
    rotated `refresh_token`). Raises `ExpiredCredentialError` on `invalid_grant` (not retryable),
    `NonRetryableAgentError` for a misconfigured client, and a retryable `AgentError` for network
    trouble or a 5xx.
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        response = await client.post(token_uri, data=data)
    except httpx.HTTPError as exc:
        raise AgentError("Couldn't reach Google to refresh the connection.", code="google_unreachable") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 200:
        return response.json()
    try:
        error = response.json().get("error", "")
    except ValueError:
        error = ""
    if error == "invalid_grant":
        raise ExpiredCredentialError()
    if error in ("invalid_client", "unauthorized_client") or response.status_code in (400, 401):
        raise NonRetryableAgentError(MISCONFIGURED_MESSAGE, code="google_misconfigured")
    raise AgentError("Google couldn't refresh the connection right now.", code="google_unavailable")


# ---------------------------------------------------------------- placeholders for "no connection"
class NoGooglePublisher:
    """What a real-mode run gets when the Publisher node names no Google account."""

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        raise MissingCredentialError()


class NoGoogleEmail:
    async def send(self, to: list[str], subject: str, body: str) -> str:
        raise MissingCredentialError()


def google_ports(credential: Mapping[str, Any]) -> tuple[dict[str, PublishPort], EmailPort]:
    """The publishers and email port for one resolved Google credential."""
    from adapters.email.gmail import GmailEmail
    from adapters.publish.drive import DrivePublisher
    from adapters.publish.youtube import YouTubePublisher

    info = dict(credential)
    return {"youtube": YouTubePublisher(info), "drive": DrivePublisher(info)}, GmailEmail(info)
