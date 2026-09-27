"""Credential encryption (D-09) and the credentials table's one-row-per-account rule."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.crypto import CredentialCipher, CredentialDecryptError, CredentialKeyError
from db.models import Base, Credential, User

PAYLOAD = {"access_token": "ya29.secret-access", "refresh_token": "1//0secret-refresh", "scope": "a b"}


def test_round_trip_and_ciphertext_hides_the_tokens():
    cipher = CredentialCipher(Fernet.generate_key().decode())
    blob = cipher.encrypt(PAYLOAD)
    assert b"secret" not in blob and b"ya29" not in blob
    assert cipher.decrypt(blob) == PAYLOAD


def test_a_different_key_cannot_decrypt():
    blob = CredentialCipher(Fernet.generate_key().decode()).encrypt(PAYLOAD)
    with pytest.raises(CredentialDecryptError):
        CredentialCipher(Fernet.generate_key().decode()).decrypt(blob)


def test_tampering_is_detected():
    cipher = CredentialCipher(Fernet.generate_key().decode())
    blob = bytearray(cipher.encrypt(PAYLOAD))
    blob[40] ^= 1
    with pytest.raises(CredentialDecryptError):
        cipher.decrypt(bytes(blob))


def test_rotation_new_key_first_old_key_still_reads():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    blob = CredentialCipher(old).encrypt(PAYLOAD)
    rotating = CredentialCipher(f"{new},{old}")
    assert rotating.decrypt(blob) == PAYLOAD
    rotated = rotating.rotate(blob)
    assert CredentialCipher(new).decrypt(rotated) == PAYLOAD


@pytest.mark.parametrize("key", [None, "", "not-a-fernet-key"])
def test_missing_or_bad_key_is_a_clear_error(key):
    with pytest.raises(CredentialKeyError):
        CredentialCipher(key)


def test_one_row_per_user_provider_account():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="a@b.co")
        s.add(user)
        s.flush()
        for _ in range(2):
            s.add(Credential(user_id=user.id, provider="google", account_email="x@gmail.com", encrypted_payload=b"x"))
        with pytest.raises(IntegrityError):
            s.flush()
