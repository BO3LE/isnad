from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath


class LocalStorage:
    """StoragePort on the local filesystem — development and tests.

    Paths follow the agreed shape `artifacts/{user}/{run}/...` (GP-plan W4). Production uses
    `adapters.storage.supabase.SupabaseStorage` with the same paths.
    """

    def __init__(self, root: str | Path, public_base_url: str = "http://localhost:8000/files"):
        self._root = Path(root)
        self._base = public_base_url.rstrip("/")

    def _resolve(self, path: str) -> Path:
        clean = PurePosixPath(path)
        if clean.is_absolute() or ".." in clean.parts:
            raise ValueError(f"invalid storage path: {path}")
        return self._root.joinpath(*clean.parts)

    async def put(self, path: str, data: bytes, content_type: str) -> str:
        target = self._resolve(path)

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await asyncio.to_thread(write)
        return path

    async def get(self, path: str) -> bytes:
        return await asyncio.to_thread(self._resolve(path).read_bytes)

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        self._resolve(path)
        return f"{self._base}/{path}"
