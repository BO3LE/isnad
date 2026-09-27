from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote

from contracts.errors import AgentError, NonRetryableAgentError


class SupabaseStorage:
    """StoragePort backed by a private Supabase Storage bucket, served by signed URL (GP-plan W4).

    Interchangeable with `adapters.storage.local.LocalStorage`: same paths, same return values,
    same `ValueError` on a path that tries to escape the bucket. The bucket is called `artifacts`,
    and the worker files every run under `{user_id}/{run_id}/`, so an object's full location is
    the agreed `artifacts/{user}/{run}/{file}` — the same layout as `STORAGE_ROOT` in development.

    Talks to the Storage REST API with the project's service key, which bypasses RLS: it belongs in
    the worker only and must never reach a browser. Install with `gp-adapters[storage]` (httpx).
    """

    def __init__(self, url: str, service_key: str, bucket: str = "artifacts", timeout: float = 30.0):
        if not url or not service_key:
            raise ValueError("SupabaseStorage needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self._url, self._key, self._bucket = url.rstrip("/"), service_key, bucket
        self._timeout = timeout

    # --- helpers -------------------------------------------------------------------

    @staticmethod
    def _resolve(path: str) -> str:
        """Validate `path` the way LocalStorage does and return it URL-encoded."""
        clean = PurePosixPath(path)
        if not path or clean.is_absolute() or ".." in clean.parts or not clean.parts:
            raise ValueError(f"invalid storage path: {path}")
        return quote(str(clean), safe="/")

    def _object_url(self, path: str, *, sign: bool = False) -> str:
        kind = "object/sign" if sign else "object"
        return f"{self._url}/storage/v1/{kind}/{self._bucket}/{self._resolve(path)}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "apikey": self._key}

    def _client(self):
        import httpx

        return httpx.AsyncClient(timeout=self._timeout)

    @staticmethod
    def _body(response) -> dict:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    @classmethod
    def _effective_status(cls, response) -> int:
        """Supabase wraps most storage failures in HTTP 400 and puts the real code in the body.

        A missing object comes back as `400 {"statusCode":"404","error":"not_found",...}`, so
        trusting `response.status_code` alone would file every server-side fault as permanent.
        """
        if response.status_code != 400:
            return response.status_code
        try:
            return int(cls._body(response).get("statusCode", 400))
        except (TypeError, ValueError):
            return 400

    @classmethod
    def _raise_for(cls, response, action: str) -> None:
        """Map a Supabase Storage error response onto the agent error vocabulary."""
        if response.status_code < 400:
            return
        status = cls._effective_status(response)
        body = cls._body(response)
        if body.get("code") == "NoSuchBucket" or body.get("error") == "Bucket not found":
            raise NonRetryableAgentError("File storage isn't set up correctly.", code="storage_no_bucket")
        if status in (401, 403):
            raise NonRetryableAgentError("File storage isn't set up correctly.", code="storage_auth")
        if status == 404:
            raise NonRetryableAgentError("That file isn't in storage any more.", code="storage_not_found")
        if status == 413:
            raise NonRetryableAgentError("The file is too large to store.", code="storage_too_large")
        if status == 429:
            raise AgentError("File storage is busy.", code="storage_rate_limited")
        if status < 500:
            raise NonRetryableAgentError(f"File storage rejected the {action} ({status}).", code="storage_rejected")
        raise AgentError(f"File storage returned an error ({status}).", code="storage_error")

    async def _send(self, method: str, url: str, **kwargs):
        import httpx

        try:
            async with self._client() as client:
                return await client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise AgentError("Couldn't reach file storage.", code="storage_unreachable") from exc

    # --- StoragePort ---------------------------------------------------------------

    async def put(self, path: str, data: bytes, content_type: str) -> str:
        url = self._object_url(path)
        # x-upsert: a retried step rewrites its own file instead of failing on "already exists".
        headers = {**self._headers, "Content-Type": content_type, "x-upsert": "true"}
        response = await self._send("POST", url, content=data, headers=headers)
        self._raise_for(response, "upload")
        return path

    async def get(self, path: str) -> bytes:
        response = await self._send("GET", self._object_url(path), headers=self._headers)
        self._raise_for(response, "download")
        return response.content

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        url = self._object_url(path, sign=True)
        response = await self._send("POST", url, json={"expiresIn": expires_in}, headers=self._headers)
        self._raise_for(response, "signing")
        body = self._body(response)
        signed = body.get("signedURL") or body.get("signedUrl")
        if not signed:
            raise AgentError("File storage didn't return a download link.", code="storage_no_link")
        if signed.startswith("http"):
            return signed
        # Supabase returns a path relative to /storage/v1 (e.g. "/object/sign/artifacts/…?token=…").
        return f"{self._url}/storage/v1/{signed.lstrip('/')}"
