from __future__ import annotations


class SupabaseStorage:
    """StoragePort backed by a Supabase Storage bucket, served by signed URL.

    TODO(W4, Mohammed/Zain): implement with the Supabase Storage REST API once D-01 is signed off.
    Paths: artifacts/{user}/{run}/{file}.
    """

    def __init__(self, url: str, service_key: str, bucket: str = "artifacts"):
        self._url, self._key, self._bucket = url, service_key, bucket

    async def put(self, path: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError("Supabase storage lands in W4")

    async def get(self, path: str) -> bytes:
        raise NotImplementedError("Supabase storage lands in W4")

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        raise NotImplementedError("Supabase storage lands in W4")
