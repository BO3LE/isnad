from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.auth import InvalidToken, verify_token
from api.catalog import CatalogSource, RedisCatalog
from api.queue import CeleryEnqueuer, Enqueuer
from api.settings import ApiSettings, get_settings
from db.models import User
from db.session import make_engine, make_session_factory

bearer = HTTPBearer(auto_error=False)


@lru_cache
def _session_factory(database_url: str) -> sessionmaker[Session]:
    return make_session_factory(make_engine(database_url))


def get_session(settings: ApiSettings = Depends(get_settings)) -> Iterator[Session]:
    with _session_factory(settings.database_url)() as session:
        yield session


@lru_cache
def _enqueuer(broker_url: str) -> CeleryEnqueuer:
    return CeleryEnqueuer(broker_url)


def get_enqueuer(settings: ApiSettings = Depends(get_settings)) -> Enqueuer:
    return _enqueuer(settings.redis_url)


@lru_cache
def _catalog(redis_url: str) -> RedisCatalog:
    return RedisCatalog(redis_url)


def get_catalog(settings: ApiSettings = Depends(get_settings)) -> CatalogSource:
    return _catalog(settings.redis_url)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
    settings: ApiSettings = Depends(get_settings),
) -> User:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        user_id, email = verify_token(settings, credentials.credentials)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your session has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = session.get(User, user_id)
    if user is None:
        # First request from a Supabase-authenticated user: mirror them into `users`.
        existing = session.scalar(select(User).where(User.email == email)) if email else None
        if existing is not None:
            return existing
        user = User(id=user_id, email=email or f"{user_id}@unknown.local")
        session.add(user)
        session.commit()
    return user


def owned(user: User, owner_id: UUID) -> None:
    """Other users' rows are 404, never 403 — their existence is not revealed."""
    if user.id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
