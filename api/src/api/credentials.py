"""Encryption for third-party OAuth tokens stored in the credentials table."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_payload(secret: str, payload: dict[str, Any]) -> bytes:
    return _fernet(secret).encrypt(json.dumps(payload, separators=(",", ":")).encode())


def decrypt_payload(secret: str, payload: bytes) -> dict[str, Any]:
    return json.loads(_fernet(secret).decrypt(payload))
