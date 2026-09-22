"""JWT verification.

Two token shapes are accepted, both carrying `sub` = user id, `email`, `aud` = "authenticated":

- HS256, signed with `jwt_secret` — issued by `POST /auth/dev-login` for local development.
- Whatever algorithm the Supabase project's *current* signing key uses. Supabase moved from a
  single HS256 shared secret to asymmetric signing keys (ES256/RS256), and the isnad project has
  already rotated to one — so these are verified against the project's public JWKS
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`), never a shared secret. That also means Supabase
  rotating its key again needs no change here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from jwt import PyJWKClient

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


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def verify_token(settings: ApiSettings, token: str) -> tuple[uuid.UUID, str]:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience)
        else:
            jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
            signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(token, signing_key.key, algorithms=[alg], audience=settings.jwt_audience)
        return uuid.UUID(claims["sub"]), claims.get("email", "")
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc
