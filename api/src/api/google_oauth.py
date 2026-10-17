"""Google OAuth 2.0 (web server flow) for Connections (D-09).

The API never imports `adapters`, so the three calls the connect/disconnect flow needs — build the
consent URL, exchange the code, revoke — live here. Refreshing a token during a run is the worker's
job (`worker.credentials`).

`state` is a short-lived HS256 JWT signed with JWT_SECRET: it names the Isnad user who pressed
Connect, a nonce, which access is being asked for, and whether the browser is a popup. Its nonce
must also match the HttpOnly cookie set on the response to POST /connections/google/start, so a
consent link can't be replayed in someone else's browser.

Google won't grant YouTube and Drive in one consent: asked for `youtube.upload` with `drive.file`,
it stops at "Access blocked: Authorisation error — This request contains scopes that cannot be
requested together" (Error 400 invalid_request; seen with this app's client, 2026-10-17). YouTube
alone, YouTube with Gmail and Drive with Gmail are each accepted. So a Google account is connected
once per *access* — YouTube, or Drive and Gmail — and each is its own connection with its own
refresh token (see `ACCESS`).
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt

from api.settings import ApiSettings

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"

PROVIDER = "google"

YOUTUBE = "https://www.googleapis.com/auth/youtube.upload"
DRIVE = "https://www.googleapis.com/auth/drive.file"  # only files Isnad created — not the rest of Drive
GMAIL = "https://www.googleapis.com/auth/gmail.send"
# Who the account is; asked for in every consent.
IDENTITY = ["openid", "https://www.googleapis.com/auth/userinfo.email"]

Access = Literal["youtube", "drive_gmail"]
# What Publisher (YouTube, Drive) and Email (Gmail) need, in the groups Google grants together.
ACCESS: dict[str, list[str]] = {
    "youtube": [YOUTUBE],
    "drive_gmail": [DRIVE, GMAIL],
}
# Scopes as a person reads them on S-09 ("YouTube", "Drive · Gmail").
SCOPE_LABELS = {YOUTUBE: "YouTube", DRIVE: "Drive", GMAIL: "Gmail"}

STATE_AUDIENCE = "isnad:google-oauth"
STATE_TTL = timedelta(minutes=10)
NONCE_COOKIE = "isnad_google_oauth"

Mode = Literal["redirect", "popup"]


class OAuthError(Exception):
    """Something the person can retry: Google refused, or the round trip was tampered with or too slow."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class State:
    user_id: uuid.UUID
    nonce: str
    mode: Mode
    access: Access


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def make_state(settings: ApiSettings, user_id: uuid.UUID, nonce: str, mode: Mode, access: Access) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "nonce": nonce,
        "mode": mode,
        "access": access,
        "aud": STATE_AUDIENCE,
        "iat": now,
        "exp": now + STATE_TTL,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def read_state(settings: ApiSettings, token: str, cookie_nonce: str | None) -> State:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=STATE_AUDIENCE)
        state = State(
            user_id=uuid.UUID(claims["sub"]),
            nonce=str(claims["nonce"]),
            mode=claims.get("mode", "redirect"),
            access=claims["access"],
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise OAuthError("state") from None
    if state.mode not in ("redirect", "popup") or state.access not in ACCESS:
        raise OAuthError("state")
    if settings.oauth_bind_browser and not (cookie_nonce and hmac.compare_digest(cookie_nonce, state.nonce)):
        raise OAuthError("state")
    return state


def scopes_for(access: Access) -> list[str]:
    return [*IDENTITY, *ACCESS[access]]


def authorization_url(settings: ApiSettings, state: str, access: Access) -> str:
    # No include_granted_scopes: it would fold the account's other access into this consent, which
    # is the YouTube-with-Drive request Google refuses.
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes_for(access)),
        "access_type": "offline",  # a refresh token, so runs work when the person is not around
        "prompt": "consent",  # …issued again on every connect, not only the first
        "state": state,
    }
    return f"{AUTH_URI}?{urlencode(params)}"


async def exchange_code(settings: ApiSettings, code: str, client: httpx.AsyncClient) -> dict[str, Any]:
    try:
        response = await client.post(
            TOKEN_URI,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
            },
        )
    except httpx.HTTPError:
        raise OAuthError("unreachable") from None
    if response.status_code != 200:
        raise OAuthError("exchange")
    tokens = response.json()
    if not tokens.get("access_token"):
        raise OAuthError("exchange")
    return tokens


def account_email(settings: ApiSettings, id_token: str | None) -> str:
    """The Google account's address, from the ID token Google returned with the tokens.

    It came straight from Google's token endpoint over TLS, so (per OpenID Connect Core §3.1.3.7)
    its signature need not be re-checked; the audience and issuer still are.
    """
    if not id_token:
        raise OAuthError("email")
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False}, algorithms=["RS256"])
    except jwt.PyJWTError:
        raise OAuthError("email") from None
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if settings.google_client_id not in audiences:
        raise OAuthError("email")
    if claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise OAuthError("email")
    email = claims.get("email")
    if not email:
        raise OAuthError("email")
    return str(email).lower()


async def revoke(token: str, client: httpx.AsyncClient) -> bool:
    """Best effort: a token Google already forgot is as good as revoked."""
    try:
        response = await client.post(REVOKE_URI, data={"token": token})
    except httpx.HTTPError:
        return False
    return response.status_code in (200, 400)


def grants_a_service(scopes: list[str], access: Access) -> bool:
    """Google's consent screen lets a person untick scopes. A connection that grants none of what it
    asked for could do nothing for any step, so it is refused rather than stored."""
    return any(scope in scopes for scope in ACCESS[access])


def plain_scopes(scopes: list[str]) -> list[str]:
    return [label for scope, label in SCOPE_LABELS.items() if scope in scopes]
