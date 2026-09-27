"""Connections (S-09, D-09): connect a Google account, list, disconnect.

Tokens go one way only — from Google into `credentials.encrypted_payload`. No response of this
router, no log line and no workflow ever contains one. A step refers to a connection by its `id`.

    POST   /connections/google/start     → {authorization_url}; the browser (or a popup) goes there
    GET    /connections/google/callback  ← Google redirects here; stores the tokens, returns to the app
    GET    /connections                  → the signed-in user's connections
    DELETE /connections/{id}             → revoke at Google (best effort) and forget
"""

from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import google_oauth
from api.deps import get_current_user, get_session, owned
from api.schemas import Connection, ConnectStart
from api.services.credentials import status_of, usage_counts
from api.settings import ApiSettings, get_settings
from db.crypto import CredentialCipher, CredentialDecryptError, CredentialKeyError
from db.models import Credential, User

router = APIRouter(prefix="/connections", tags=["connections"])
log = logging.getLogger(__name__)

NOT_SET_UP = "Google connections aren't set up on this server yet."


def get_google_transport() -> httpx.AsyncBaseTransport | None:
    """The HTTP transport for calls to Google. Tests override it with `httpx.MockTransport`."""
    return None


def _client(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, timeout=15)


def _cipher(settings: ApiSettings) -> CredentialCipher:
    if not settings.google_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)
    try:
        return CredentialCipher(settings.credentials_encryption_key)
    except CredentialKeyError:
        log.error("CREDENTIALS_ENCRYPTION_KEY is not a valid Fernet key")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP) from None


def _connection(row: Credential, used_by: int) -> Connection:
    return Connection(
        id=row.id,
        provider="google",
        account_email=row.account_email,
        scopes=google_oauth.plain_scopes(list(row.scopes or [])),
        status=status_of(row),
        expires_at=row.expires_at,
        created_at=row.created_at,
        used_by=used_by,
    )


@router.get("", response_model=list[Connection])
def list_connections(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Credential).where(Credential.user_id == user.id).order_by(Credential.created_at)
    ).all()
    counts = usage_counts(session, user.id)
    return [_connection(row, counts.get(str(row.id), 0)) for row in rows]


@router.post(
    "/google/start",
    response_model=ConnectStart,
    responses={503: {"description": "Google connections aren't configured on this server"}},
)
def start_google(
    response: Response,
    mode: Literal["redirect", "popup"] = Query(
        "redirect", description="`popup`: the callback answers with a page that tells the opener and closes."
    ),
    user: User = Depends(get_current_user),
    settings: ApiSettings = Depends(get_settings),
):
    """Begin connecting a Google account. Call with `credentials: "include"` so the browser keeps the
    cookie that ties Google's answer to this browser; then open `authorization_url`."""
    _cipher(settings)
    nonce = google_oauth.new_nonce()
    state = google_oauth.make_state(settings, user.id, nonce, mode)
    response.set_cookie(
        google_oauth.NONCE_COOKIE,
        nonce,
        max_age=int(google_oauth.STATE_TTL.total_seconds()),
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return ConnectStart(authorization_url=google_oauth.authorization_url(settings, state))


def _finish(settings: ApiSettings, mode: str, *, error: str | None = None) -> Response:
    """Back to the app: a redirect to Connections, or — in a popup — a page that tells the opener."""
    query = {"error": f"google_{error}"} if error else {"connected": "google"}
    target = f"{settings.frontend_url.rstrip('/')}/settings/connections?{urlencode(query)}"
    if mode != "popup":
        response: Response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    else:
        message = json.dumps({"type": "isnad:google-connection", "ok": error is None, "error": error})
        origin = json.dumps(settings.frontend_url.rstrip("/"))
        page = f"""<!doctype html><meta charset="utf-8"><title>Isnad</title>
<p>{"Google connected. You can close this window." if error is None else "Google wasn't connected. You can try again."}
<a href="{html.escape(target)}">Back to Isnad</a></p>
<script>
if (window.opener) {{ window.opener.postMessage({message}, {origin}); window.close(); }}
else {{ window.location.replace({json.dumps(target)}); }}
</script>"""
        response = HTMLResponse(page)
    response.delete_cookie(google_oauth.NONCE_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
    transport: httpx.AsyncBaseTransport | None = Depends(get_google_transport),
):
    """Where Google sends the browser back. Identified by `state`, not by a bearer token."""
    try:
        claims = google_oauth.read_state(settings, state, request.cookies.get(google_oauth.NONCE_COOKIE))
    except google_oauth.OAuthError:
        return _finish(settings, "redirect", error="state")
    if error or not code:
        # access_denied: the person pressed Cancel on Google's screen.
        return _finish(settings, claims.mode, error="denied")
    if not settings.google_configured:
        return _finish(settings, claims.mode, error="unavailable")
    cipher = _cipher(settings)
    if session.get(User, claims.user_id) is None:
        return _finish(settings, claims.mode, error="state")

    try:
        async with _client(transport) as client:
            tokens = await google_oauth.exchange_code(settings, code, client)
        email = google_oauth.account_email(settings, tokens.get("id_token"))
    except google_oauth.OAuthError as exc:
        log.warning("google connect failed for user %s: %s", claims.user_id, exc.reason)
        return _finish(settings, claims.mode, error="failed")

    now = datetime.now(UTC)
    granted = str(tokens.get("scope", "")).split()
    row = session.scalar(
        select(Credential).where(
            Credential.user_id == claims.user_id,
            Credential.provider == google_oauth.PROVIDER,
            Credential.account_email == email,
        )
    )
    previous_refresh = None
    if row is not None:
        try:
            previous_refresh = cipher.decrypt(row.encrypted_payload).get("refresh_token")
        except CredentialDecryptError:
            previous_refresh = None
    refresh_token = tokens.get("refresh_token") or previous_refresh
    if not refresh_token:
        # Without one no run could act later. prompt=consent makes Google send it, so this is rare.
        return _finish(settings, claims.mode, error="failed")

    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": refresh_token,
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": " ".join(granted),
        "access_token_expires_at": (now + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat(),
    }
    # Google limits refresh tokens of apps in "Testing" (7 days) and says so here; otherwise no end date.
    lifetime = tokens.get("refresh_token_expires_in")
    expires_at = now + timedelta(seconds=int(lifetime)) if lifetime else None

    if row is None:
        row = Credential(user_id=claims.user_id, provider=google_oauth.PROVIDER, account_email=email)
        session.add(row)
    row.scopes = granted
    row.encrypted_payload = cipher.encrypt(payload)
    row.expires_at = expires_at
    row.invalid_at = None
    row.updated_at = now
    session.commit()
    log.info("google account connected for user %s (credential %s)", claims.user_id, row.id)
    return _finish(settings, claims.mode)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    credential_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
    transport: httpx.AsyncBaseTransport | None = Depends(get_google_transport),
):
    """Forget a connection. Steps that used it then show "needs a Google connection"."""
    row = session.get(Credential, credential_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    owned(user, row.user_id)

    token = None
    try:
        payload = CredentialCipher(settings.credentials_encryption_key).decrypt(row.encrypted_payload)
        token = payload.get("refresh_token") or payload.get("access_token")
    except (CredentialKeyError, CredentialDecryptError):
        token = None
    if token:
        async with _client(transport) as client:
            if not await google_oauth.revoke(token, client):
                log.warning("couldn't revoke credential %s at Google; deleting it anyway", row.id)

    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
