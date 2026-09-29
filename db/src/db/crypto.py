"""Encryption for `credentials.encrypted_payload` (D-09, PROPOSED).

The `db` component owns the credentials table, so it owns the format of the one column that holds a
secret. Both writers of that column already depend on `db` — the api (OAuth callback) and the worker
(token refresh) — and neither may import the other, so this is the one place both can share.

Format: a Fernet token (AES-128-CBC + HMAC-SHA256, versioned and timestamped) over UTF-8 JSON.
Keys come from `CREDENTIALS_ENCRYPTION_KEY`: one url-safe base64 Fernet key, or several separated
by commas for rotation. The first key encrypts; every key is tried when decrypting (MultiFernet), so
rotating is: put the new key first, run `rotate()` over the rows, then drop the old key.

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The payload is a plain dict. For provider "google" it is:
    {"access_token": str, "refresh_token": str, "token_type": "Bearer",
     "scope": "space separated", "access_token_expires_at": ISO-8601 UTC}
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

__all__ = ["CredentialCipher", "CredentialDecryptError", "CredentialKeyError"]


class CredentialKeyError(RuntimeError):
    """`CREDENTIALS_ENCRYPTION_KEY` is missing or malformed."""


class CredentialDecryptError(RuntimeError):
    """The payload was not encrypted with any configured key, or was tampered with."""


class CredentialCipher:
    def __init__(self, keys: str | list[str] | None):
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",")]
        keys = [k for k in (keys or []) if k]
        if not keys:
            raise CredentialKeyError(
                "CREDENTIALS_ENCRYPTION_KEY is not set. Generate one with "
                '`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.'
            )
        try:
            self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
        except (ValueError, TypeError) as exc:
            raise CredentialKeyError("CREDENTIALS_ENCRYPTION_KEY is not a valid Fernet key.") from exc

    def encrypt(self, payload: dict[str, Any]) -> bytes:
        return self._fernet.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def decrypt(self, token: bytes) -> dict[str, Any]:
        try:
            return json.loads(self._fernet.decrypt(bytes(token)).decode("utf-8"))
        except InvalidToken as exc:
            raise CredentialDecryptError("A stored credential could not be decrypted with the configured key.") from exc

    def rotate(self, token: bytes) -> bytes:
        """Re-encrypt with the first (newest) key."""
        return self._fernet.rotate(bytes(token))
