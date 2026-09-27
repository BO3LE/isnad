"""Google OAuth 2.0 (web server flow) for Connections (D-09).

The API never imports `adapters`, so the three calls the connect/disconnect flow needs — build the
consent URL, exchange the code, revoke — live here. Refreshing a token during a run is the worker's
job (`worker.credentials`).

`state` is a short-lived HS256 JWT signed with JWT_SECRET: it names the Isnad user who pressed
Connect, a nonce, and whether the browser is a popup. Its nonce must also match the HttpOnly cookie
set on the response to POST /connections/google/start, so a consent link can't be replayed in
someone else's browser.
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

# What Publisher (YouTube, Drive) and Email (Gmail) need, plus who the account is.
# drive.file only reaches files Isnad created — not the rest of the user's Drive.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
]
# Scopes as a person reads them on S-09 ("YouTube · Drive · Gmail").
SCOPE_LABELS = {
    "https://www.googleapis.com/auth/youtube.upload": "YouTube",
    "https://www.googleapis.com/auth/drive.file": "Drive",
    "https://www.googleapis.com/auth/gmail.send": "Gmail",
}

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


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def make_state(settings: ApiSettings, user_id: uuid.UUID, nonce: str, mode: Mode) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "nonce": nonce,
        "mode": mode,
        "aud": STATE_AUDIENCE,
        "iat": now,
        "exp": now + STATE_TTL,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def read_state(settings: ApiSettings, token: str, cookie_nonce: str | None) -> State:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=STATE_AUDIENCE)
        state = State(user_id=uuid.UUID(claims["sub"]), nonce=str(claims["nonce"]), mode=claims.get("mode", "redirect"))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise OAuthError("state") from None
    if state.mode not in ("redirect", "popup"):
        raise OAuthError("state")
    if settings.oauth_bind_browser and not (cookie_nonce and hmac.compare_digest(cookie_nonce, state.nonce)):
        raise OAuthError("state")
    return state


def authorization_url(settings: ApiSettings, state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # a refresh token, so runs work when the person is not around
        "prompt": "consent",  # …issued again on every connect, not only the first
        "include_granted_scopes": "true",
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


def plain_scopes(scopes: list[str]) -> list[str]:
    return [label for scope, label in SCOPE_LABELS.items() if scope in scopes]
