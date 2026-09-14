from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import issue_token
from api.deps import get_current_user, get_session
from api.schemas import DevLoginRequest, Me, TokenResponse
from api.settings import ApiSettings, get_settings
from db.models import User

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
