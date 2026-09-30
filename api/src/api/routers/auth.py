from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import InvalidToken, issue_oauth_state, issue_token, verify_oauth_state
from api.deps import get_current_user, get_session
from api.schemas import DevLoginRequest, GoogleConnect, GoogleConnectionStatus, GoogleConnectRequest, Me, TokenResponse
from api.settings import ApiSettings, get_settings
from db.credentials import encrypt_payload
from db.models import Credential, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-login", response_model=TokenResponse)
def dev_login(
    body: DevLoginRequest, session: Session = Depends(get_session), settings: ApiSettings = Depends(get_settings)
):
    """Development only: sign in as any email, no password. Disabled when ENVIRONMENT=production.

    TODO(W2, Hasan): /auth/register and /auth/login — delegated to Supabase Auth once D-01 is signed off.
    """
    if not settings.dev_login_allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    email = body.email.lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(id=uuid.uuid4(), email=email)
        session.add(user)
        session.commit()
    return TokenResponse(access_token=issue_token(settings, user.id, user.email))


@router.get("/me", response_model=Me)
def me(user: User = Depends(get_current_user)):
    return Me(id=user.id, email=user.email)


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def _scope_for(provider: str) -> str:
    return YOUTUBE_UPLOAD_SCOPE if provider == "youtube" else DRIVE_FILE_SCOPE


def _google_client(settings: ApiSettings) -> dict[str, dict[str, object]]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "YouTube is not configured yet.")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_oauth_redirect_uri],
        }
    }


@router.post("/google/connect", response_model=GoogleConnect)
def google_connect(
    body: GoogleConnectRequest, user: User = Depends(get_current_user), settings: ApiSettings = Depends(get_settings)
):
    """Return Google's consent URL; the browser navigates there only after the user chooses to connect."""
    from google_auth_oauthlib.flow import Flow

    # This is a confidential server-side web client.  We rebuild Flow on the callback,
    # so do not let the library generate an in-memory PKCE verifier that would be lost
    # between the two HTTP requests.
    flow = Flow.from_client_config(
        _google_client(settings),
        scopes=[_scope_for(body.provider)],
        redirect_uri=settings.google_oauth_redirect_uri,
        autogenerate_code_verifier=False,
    )
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", state=issue_oauth_state(settings, user.id, body.provider)
    )
    return GoogleConnect(authorization_url=url)


@router.get("/google/status", response_model=GoogleConnectionStatus)
def google_status(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Report connection state without exposing any OAuth token or account data."""
    providers = set(session.scalars(select(Credential.provider).where(Credential.user_id == user.id)).all())
    return GoogleConnectionStatus(youtube_connected="youtube" in providers, drive_connected="drive" in providers)


@router.get("/google/callback")
def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
):
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google connection was cancelled.")
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google did not return an authorization code.")
    try:
        user_id, provider = verify_oauth_state(settings, state)
    except InvalidToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This Google connection link expired. Try again.") from None

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        _google_client(settings),
        scopes=[_scope_for(provider)],
        redirect_uri=settings.google_oauth_redirect_uri,
        autogenerate_code_verifier=False,
    )
    # Google can return harmless OpenID identity scopes that were granted in an
    # earlier consent session. The uploader still requests and uses only the
    # YouTube upload scope, so don't reject the token merely for that superset.
    flow.oauth2session.scope = None
    flow.fetch_token(code=code)
    credentials = flow.credentials
    payload = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "scopes": list(credentials.scopes or []),
    }
    existing = session.scalar(
        select(Credential)
        .where(Credential.user_id == user_id, Credential.provider == provider)
        .order_by(Credential.created_at.desc())
    )
    encrypted = encrypt_payload(settings.jwt_secret, payload)
    if existing:
        existing.encrypted_payload = encrypted
        existing.expires_at = credentials.expiry
    else:
        session.add(
            Credential(user_id=user_id, provider=provider, encrypted_payload=encrypted, expires_at=credentials.expiry)
        )
    session.commit()
    return RedirectResponse(
        f"{settings.google_oauth_success_url}?youtube=connected", status_code=status.HTTP_303_SEE_OTHER
    )
