"""Signed download links for files in the private Supabase Storage bucket (GP-plan W4).

The API never streams files: it hands the browser a short-lived signed URL. This is the only
Storage call the API makes, so it is written here against the REST API rather than importing the
worker-side `adapters` package (C2 must not import adapters — see .importlinter).

The service key bypasses RLS. It stays on the server; only the signed URL leaves it.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import quote

import httpx


class FileMissing(Exception):
    """The object is not in the bucket (or the stored path is not a valid object key)."""


class StorageUnavailable(Exception):
    """Storage could not be reached or refused the request — not the user's fault."""


class FileSigner(Protocol):
    def sign(self, path: str, expires_in: int) -> str: ...


class SupabaseSigner:
    def __init__(self, url: str, service_key: str, bucket: str = "artifacts", timeout: float = 10.0):
        if not url or not service_key:
            raise ValueError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self._url, self._key, self._bucket, self._timeout = url.rstrip("/"), service_key, bucket, timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout)

    @staticmethod
    def _body(response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def sign(self, path: str, expires_in: int) -> str:
        clean = PurePosixPath(path)
        if not path or clean.is_absolute() or ".." in clean.parts:
            raise FileMissing(path)
        endpoint = f"{self._url}/storage/v1/object/sign/{self._bucket}/{quote(str(clean), safe='/')}"
        headers = {"Authorization": f"Bearer {self._key}", "apikey": self._key}
        try:
            with self._client() as client:
                response = client.post(endpoint, json={"expiresIn": expires_in}, headers=headers)
        except httpx.HTTPError as exc:
            raise StorageUnavailable("unreachable") from exc

        body = self._body(response)
        status = response.status_code
        if status == 400:  # Supabase wraps most failures in a 400 with the real code in the body
            try:
                status = int(body.get("statusCode", 400))
            except (TypeError, ValueError):
                status = 400
        if status == 404 and body.get("code") != "NoSuchBucket" and body.get("error") != "Bucket not found":
            raise FileMissing(path)
        if response.status_code >= 400:
            raise StorageUnavailable(f"status {status}")

        signed = body.get("signedURL") or body.get("signedUrl")
        if not signed:
            raise StorageUnavailable("no signedURL in response")
        if signed.startswith("http"):
            return signed
        # Relative to /storage/v1, e.g. "/object/sign/artifacts/…?token=…".
        return f"{self._url}/storage/v1/{signed.lstrip('/')}"
