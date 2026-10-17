"""Unit tests for JWT verification (api/src/api/auth.py): the HS256 dev-login path and the
JWKS-verified path used for Supabase-issued tokens, which sign with an asymmetric key instead."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api import deps
from api.auth import InvalidToken, issue_token, supabase_email_confirmed, verify_token
from api.deps import get_session
from api.main import create_app
from api.settings import PLACEHOLDER_JWT_SECRET, ApiSettings, get_settings
from db.models import User

SETTINGS = ApiSettings(
    environment="test",
    jwt_secret="test-secret-that-is-long-enough-for-hs256",
    storage_root="/nonexistent",
    supabase_url="https://isnad-test.supabase.co",
)
# As production runs: Supabase sign-in only. ENVIRONMENT=production has the same effect on tokens.
SUPABASE_ONLY = SETTINGS.model_copy(update={"enable_dev_login": False, "supabase_service_key": "service-key"})
ISSUER = "https://isnad-test.supabase.co/auth/v1"


def test_verify_token_round_trips_a_dev_login_hs256_token():
    user_id = uuid.uuid4()

    token = issue_token(SETTINGS, user_id, "demo@gp.local")

    verified = verify_token(SETTINGS, token)
    assert verified.user_id == user_id
    assert verified.email == "demo@gp.local"
    assert verified.from_dev_login


def test_verify_token_rejects_a_token_signed_with_a_different_secret():
    other = ApiSettings(environment="test", jwt_secret="a-totally-different-secret-value-32+chars", storage_root="/x")
    token = issue_token(other, uuid.uuid4(), "demo@gp.local")

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)


def test_verify_token_rejects_garbage():
    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, "not-a-jwt")


@pytest.mark.parametrize(
    "settings",
    [SUPABASE_ONLY, SETTINGS.model_copy(update={"environment": "production"})],
    ids=["dev-login-off", "production"],
)
def test_a_correctly_signed_dev_login_token_is_refused_once_dev_login_is_off(settings):
    # Whoever holds JWT_SECRET could otherwise sign in as anyone, in production too.
    token = issue_token(settings, uuid.uuid4(), "demo@gp.local")

    with pytest.raises(InvalidToken):
        verify_token(settings, token)


def test_a_dev_login_token_must_expire():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "a@b.c", "aud": SETTINGS.jwt_audience}, SETTINGS.jwt_secret, "HS256"
    )

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)


def _claims(user_id: uuid.UUID, email: str, **overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "sub": str(user_id),
        "email": email,
        "aud": SETTINGS.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=60),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _es256_token(user_id: uuid.UUID, email: str, private_key, **overrides) -> str:
    return jwt.encode(_claims(user_id, email, **overrides), private_key, algorithm="ES256", headers={"kid": "k"})


@pytest.fixture()
def supabase_key(monkeypatch):
    """The project's signing key, served by a stand-in for its JWKS endpoint (no HTTP call)."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    asked: list[str] = []

    class FakeSigningKey:
        key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token):
            return FakeSigningKey()

    def client_for(url):
        asked.append(url)
        return FakeJwksClient()

    monkeypatch.setattr("api.auth._jwks_client", client_for)
    return SimpleNamespace(private=private_key, asked=asked)


def test_verify_token_verifies_a_supabase_style_es256_token_via_jwks(supabase_key):
    """Supabase's isnad project signs with an asymmetric key (ES256), not the shared secret —
    verify_token must route a non-HS256 token through JWKS rather than jwt_secret."""
    user_id = uuid.uuid4()
    token = _es256_token(user_id, "person@example.com", supabase_key.private)

    verified = verify_token(SETTINGS, token)
    assert verified.user_id == user_id
    assert verified.email == "person@example.com"
    assert not verified.from_dev_login
    assert supabase_key.asked == [f"{ISSUER}/.well-known/jwks.json"]


def test_verify_token_rejects_an_es256_token_whose_signing_key_does_not_match(supabase_key):
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    token = _es256_token(uuid.uuid4(), "person@example.com", wrong_key)

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://someone-else.supabase.co/auth/v1"},
        {"iss": None},
        {"exp": None},
        {"aud": "anon"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
    ],
    ids=["other-project", "no-issuer", "no-expiry", "wrong-audience", "expired"],
)
def test_a_supabase_token_must_come_from_this_project_for_a_signed_in_user(supabase_key, overrides):
    token = _es256_token(uuid.uuid4(), "person@example.com", supabase_key.private, **overrides)

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)


@pytest.mark.parametrize("alg", ["none", "HS384", "HS512", "PS256"])
def test_the_token_does_not_choose_its_own_algorithm(supabase_key, alg):
    header = jwt.utils.base64url_encode(f'{{"alg":"{alg}","typ":"JWT","kid":"k"}}'.encode()).decode()
    claims = _claims(uuid.uuid4(), "a@b.c", iat=None, exp=int((datetime.now(UTC) + timedelta(hours=1)).timestamp()))
    body = jwt.utils.base64url_encode(json.dumps(claims).encode()).decode()

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, f"{header}.{body}.")
    assert supabase_key.asked == []  # refused before any key is even looked up


def test_without_supabase_configured_no_asymmetric_token_is_accepted(supabase_key):
    token = _es256_token(uuid.uuid4(), "person@example.com", supabase_key.private)

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS.model_copy(update={"supabase_url": ""}), token)


# ---------------------------------------------------------------- production refuses a weak JWT_SECRET
@pytest.mark.parametrize("secret", [PLACEHOLDER_JWT_SECRET, "short-secret", ""], ids=["example", "short", "empty"])
def test_production_refuses_to_start_with_a_weak_jwt_secret(secret):
    settings = ApiSettings(environment="production", jwt_secret=secret, storage_root="/nonexistent")

    with pytest.raises(RuntimeError, match="JWT_SECRET") as refused:
        create_app(settings)
    if secret:
        assert secret not in str(refused.value)


def test_production_starts_with_a_strong_jwt_secret():
    create_app(ApiSettings(environment="production", jwt_secret="s" * 48, storage_root="/nonexistent"))


def test_development_keeps_working_with_the_example_secret():
    create_app(ApiSettings(environment="development", jwt_secret=PLACEHOLDER_JWT_SECRET, storage_root="/x"))


# ---------------------------------------------------------------- linking a sign-in to an account by email
@pytest.fixture()
def app_for(sessions):
    def build(settings: ApiSettings) -> TestClient:
        app = create_app(settings)

        def session_override():
            with sessions() as s:
                yield s

        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    deps._confirmed_links.clear()
    yield build
    deps._confirmed_links.clear()


@pytest.fixture()
def seeded(sessions) -> uuid.UUID:
    """An account that already exists under the address — a seeded demo user, say."""
    with sessions() as s:
        user = User(id=uuid.uuid4(), email="owner@example.com")
        s.add(user)
        s.commit()
        return user.id


def _me(client: TestClient, token: str) -> httpx.Response:
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_an_unconfirmed_address_does_not_open_someone_elses_account(app_for, seeded, supabase_key, monkeypatch):
    # Signing up with someone's address must not hand over what is already under it — even with
    # `user_metadata.email_verified` set, which the user can write themselves.
    monkeypatch.setattr(deps, "supabase_email_confirmed", lambda *_a, **_k: False)
    token = _es256_token(
        uuid.uuid4(), "owner@example.com", supabase_key.private, user_metadata={"email_verified": True}
    )

    response = _me(app_for(SUPABASE_ONLY), token)

    assert response.status_code == 403
    assert response.json()["detail"] == deps.EMAIL_TAKEN


def test_a_confirmed_address_claims_the_account_and_supabase_is_asked_once(app_for, seeded, supabase_key, monkeypatch):
    asked: list[tuple] = []

    def confirmed(settings, user_id, email):
        asked.append((user_id, email))
        return True

    monkeypatch.setattr(deps, "supabase_email_confirmed", confirmed)
    supabase_id = uuid.uuid4()
    token = _es256_token(supabase_id, "Owner@Example.com", supabase_key.private)
    client = app_for(SUPABASE_ONLY)

    assert _me(client, token).json()["id"] == str(seeded)
    assert _me(client, token).json()["id"] == str(seeded)
    assert asked == [(supabase_id, "owner@example.com")]


def test_with_dev_login_on_an_address_links_as_before(app_for, seeded, supabase_key, monkeypatch):
    # Anyone can dev-login as any address there, so the address protects nothing to begin with.
    monkeypatch.setattr(deps, "supabase_email_confirmed", lambda *_a, **_k: pytest.fail("not asked"))
    token = _es256_token(uuid.uuid4(), "owner@example.com", supabase_key.private)

    assert _me(app_for(SETTINGS), token).json()["id"] == str(seeded)


def test_a_new_address_gets_its_own_account(app_for, seeded, supabase_key):
    supabase_id = uuid.uuid4()
    token = _es256_token(supabase_id, "newcomer@example.com", supabase_key.private)

    assert _me(app_for(SUPABASE_ONLY), token).json() == {"id": str(supabase_id), "email": "newcomer@example.com"}


# ---------------------------------------------------------------- asking Supabase
def _admin(status: int = 200, body=None, seen: list | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_supabase_is_asked_with_the_service_key_for_that_user():
    user_id = uuid.uuid4()
    seen: list[httpx.Request] = []
    transport = _admin(body={"email": "Owner@Example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}, seen=seen)

    assert supabase_email_confirmed(SUPABASE_ONLY, user_id, "owner@example.com", transport=transport)
    assert str(seen[0].url) == f"{ISSUER}/admin/users/{user_id}"
    assert seen[0].headers["apikey"] == "service-key"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"email": "owner@example.com", "email_confirmed_at": None}),
        (200, {"email": "someone@else.com", "email_confirmed_at": "2026-10-01T00:00:00Z"}),
        (404, {"msg": "User not found"}),
        (200, ["not", "an", "object"]),
        (200, httpx.ConnectError("down")),
    ],
    ids=["unconfirmed", "other-address", "unknown-user", "odd-body", "unreachable"],
)
def test_anything_but_a_clear_yes_from_supabase_is_no(status, body):
    transport = _admin(status, body)

    assert not supabase_email_confirmed(SUPABASE_ONLY, uuid.uuid4(), "owner@example.com", transport=transport)


def test_without_a_service_key_supabase_is_not_asked_and_the_answer_is_no():
    transport = _admin(body={"email": "owner@example.com", "email_confirmed_at": "2026-10-01T00:00:00Z"})
    settings = SUPABASE_ONLY.model_copy(update={"supabase_service_key": None})

    assert not supabase_email_confirmed(settings, uuid.uuid4(), "owner@example.com", transport=transport)
