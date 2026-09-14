"""JWT verification.

Tokens are HS256 with `sub` = user id, `email`, `aud` = "authenticated" — the same shape
Supabase Auth issues, so switching to Supabase (D-01) only changes who signs the token.
Until then, `POST /auth/dev-login` issues tokens in development.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from api.settings import ApiSettings


class InvalidToken(Exception):
    pass


def issue_token(settings: ApiSettings, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def verify_token(settings: ApiSettings, token: str) -> tuple[uuid.UUID, str]:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience)
        return uuid.UUID(claims["sub"]), claims.get("email", "")
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc
