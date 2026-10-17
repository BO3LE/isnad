from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from api.auth import InvalidToken, supabase_email_confirmed, verify_token
from api.catalog import CatalogSource, RedisCatalog
from api.queue import CeleryEnqueuer, Enqueuer
from api.settings import ApiSettings, get_settings
from api.storage import FileSigner, SupabaseSigner
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


@lru_cache
def _signer(url: str, service_key: str, bucket: str) -> SupabaseSigner:
    return SupabaseSigner(url, service_key, bucket)


def get_file_signer(settings: ApiSettings = Depends(get_settings)) -> FileSigner | None:
    """Signs download links when files live in Supabase Storage.

    None when files are on local disk, or when Supabase storage is selected but not configured —
    the outputs endpoint reports that only if the user actually asks for a file.
    """
    if settings.storage_backend != "supabase" or not settings.supabase_url or not settings.supabase_service_key:
        return None
    return _signer(settings.supabase_url, settings.supabase_service_key, settings.storage_bucket)


# (user id, email) pairs Supabase has confirmed, so the admin API is asked once per process, not
# on every request of a linked account. Only "yes" is remembered: someone who confirms later gets in.
_confirmed_links: set[tuple[UUID, str]] = set()
EMAIL_TAKEN = "This email address is already used by another account on this server."


def _may_link(settings: ApiSettings, user_id: UUID, email: str) -> bool:
    """Whether a new sign-in may take over the existing account with the same address.

    With dev login on, an address proves nothing — anyone can dev-login as anyone — so there is
    nothing to protect. Otherwise only when Supabase says this user confirmed that address: a
    seeded demo account (SEED_DEMO_EMAIL) is meant to be claimed this way, by its owner.
    """
    if settings.dev_login_allowed:
        return True
    if (user_id, email) in _confirmed_links:
        return True
    if supabase_email_confirmed(settings, user_id, email):
        if len(_confirmed_links) > 4096:
            _confirmed_links.clear()
        _confirmed_links.add((user_id, email))
        return True
    return False


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
        token = verify_token(settings, credentials.credentials)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your session has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = session.get(User, token.user_id)
    if user is None:
        # First request from a Supabase-authenticated user: mirror them into `users`.
        email = token.email.lower()
        existing = session.scalar(select(User).where(User.email == email)) if email else None
        if existing is not None:
            if _may_link(settings, token.user_id, email):
                return existing
            raise HTTPException(status.HTTP_403_FORBIDDEN, EMAIL_TAKEN)
        user = User(id=token.user_id, email=email or f"{token.user_id}@unknown.local")
        session.add(user)
        try:
            session.commit()
        except IntegrityError:  # a second first request, a moment earlier
            session.rollback()
            user = session.get(User, token.user_id)
            if user is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, EMAIL_TAKEN) from None
    return user


def owned(user: User, owner_id: UUID) -> None:
    """Other users' rows are 404, never 403 — their existence is not revealed."""
    if user.id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
