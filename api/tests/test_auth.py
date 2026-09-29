"""Unit tests for JWT verification (api/src/api/auth.py): the HS256 dev-login path and the
JWKS-verified path used for Supabase-issued tokens, which sign with an asymmetric key instead."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from api.auth import InvalidToken, issue_token, verify_token
from api.settings import ApiSettings

SETTINGS = ApiSettings(
    environment="test", jwt_secret="test-secret-that-is-long-enough-for-hs256", storage_root="/nonexistent"
)


def test_verify_token_round_trips_a_dev_login_hs256_token():
    user_id = uuid.uuid4()

    token = issue_token(SETTINGS, user_id, "demo@gp.local")

    verified_id, email = verify_token(SETTINGS, token)
    assert verified_id == user_id
    assert email == "demo@gp.local"


def test_verify_token_rejects_a_token_signed_with_a_different_secret():
    other = ApiSettings(environment="test", jwt_secret="a-totally-different-secret-value-32+chars", storage_root="/x")
    token = issue_token(other, uuid.uuid4(), "demo@gp.local")

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)


def test_verify_token_rejects_garbage():
    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, "not-a-jwt")


def _es256_token(user_id: uuid.UUID, email: str, private_key) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": SETTINGS.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=60),
    }
    return jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "test-key"})


def test_verify_token_verifies_a_supabase_style_es256_token_via_jwks(monkeypatch):
    """Supabase's isnad project signs with an asymmetric key (ES256), not the shared secret —
    verify_token must route a non-HS256 token through JWKS rather than jwt_secret."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    user_id = uuid.uuid4()
    token = _es256_token(user_id, "person@example.com", private_key)

    class FakeSigningKey:
        key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token):
            return FakeSigningKey()

    # No real HTTP call to Supabase's JWKS endpoint: the client factory is replaced outright.
    monkeypatch.setattr("api.auth._jwks_client", lambda _url: FakeJwksClient())

    verified_id, email = verify_token(SETTINGS, token)
    assert verified_id == user_id
    assert email == "person@example.com"


def test_verify_token_rejects_an_es256_token_whose_signing_key_does_not_match(monkeypatch):
    signing_key = ec.generate_private_key(ec.SECP256R1())
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    token = _es256_token(uuid.uuid4(), "person@example.com", signing_key)

    class FakeSigningKey:
        key = wrong_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token):
            return FakeSigningKey()

    monkeypatch.setattr("api.auth._jwks_client", lambda _url: FakeJwksClient())

    with pytest.raises(InvalidToken):
        verify_token(SETTINGS, token)
