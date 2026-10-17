"""JWT verification.

Two token shapes are accepted, both carrying `sub` = user id, `email`, `aud` = "authenticated":

- HS256, signed with `jwt_secret` — issued by `POST /auth/dev-login` for local development. Only
  accepted while dev login is: in production, or with ENABLE_DEV_LOGIN=false, a token signed with
  the shared secret is refused, so that secret leaking can't sign anyone in.
- ES256 or RS256, from the Supabase project's *current* signing key. Supabase moved from a single
  HS256 shared secret to asymmetric signing keys, and the isnad project has already rotated to one
  — so these are verified against the project's public JWKS
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`), never a shared secret. That also means Supabase
  rotating its key again needs no change here. The algorithm is pinned (never read from the token)
  and the issuer must be that project.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
import jwt
from jwt import PyJWKClient

from api.settings import ApiSettings

# What Supabase signs with once a project moves to asymmetric keys. Never "none", never HS256.
SUPABASE_ALGORITHMS = ["ES256", "RS256"]
REQUIRED_CLAIMS = ["exp", "sub", "aud"]


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class VerifiedToken:
    user_id: uuid.UUID
    email: str
    from_dev_login: bool  # HS256, from POST /auth/dev-login; False for a Supabase token


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
    return PyJWKClient(jwks_url, timeout=10)


def supabase_issuer(settings: ApiSettings) -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def verify_token(settings: ApiSettings, token: str) -> VerifiedToken:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not settings.dev_login_allowed:
                raise InvalidToken("dev-login tokens are not accepted here")
            claims = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                options={"require": REQUIRED_CLAIMS},
            )
            from_dev_login = True
        else:
            if alg not in SUPABASE_ALGORITHMS or not settings.supabase_url:
                raise InvalidToken("unsupported token")
            issuer = supabase_issuer(settings)
            signing_key = _jwks_client(f"{issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=SUPABASE_ALGORITHMS,
                audience=settings.jwt_audience,
                issuer=issuer,
                options={"require": [*REQUIRED_CLAIMS, "iss"]},
            )
            from_dev_login = False
        return VerifiedToken(uuid.UUID(claims["sub"]), str(claims.get("email") or ""), from_dev_login)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        # The class only: a PyJWT message can quote the claims it rejected.
        raise InvalidToken(type(exc).__name__) from exc


def supabase_email_confirmed(
    settings: ApiSettings, user_id: uuid.UUID, email: str, *, transport: httpx.BaseTransport | None = None
) -> bool:
    """Whether Supabase itself says this user confirmed `email` — asked of the Auth admin API.

    The token can't answer this: Supabase puts `email_verified` in `user_metadata`, which the user
    can rewrite with `supabase.auth.updateUser`. So before an existing account is handed to a new
    sign-in because the addresses match, the server asks. Needs SUPABASE_SERVICE_KEY; without it,
    or if Supabase can't be reached, the answer is no.
    """
    if not (settings.supabase_url and settings.supabase_service_key and email):
        return False
    key = settings.supabase_service_key
    try:
        with httpx.Client(transport=transport, timeout=10) as client:
            response = client.get(
                f"{supabase_issuer(settings)}/admin/users/{user_id}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    return bool(body.get("email_confirmed_at")) and str(body.get("email") or "").lower() == email.lower()
