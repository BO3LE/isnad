"""Per-run storage: every file an agent writes lands under `{user_id}/{run_id}/` (GP-plan W4).

The storage root (local) and the bucket (Supabase) are both called `artifacts`, so the full
location is the agreed `artifacts/{user}/{run}/...`. Agents keep writing the paths they always
have (`artifacts/videos/<id>/video.mp4`): the worker hands each run a `Ports` whose storage is
wrapped by `RunScopedStorage`, which drops the redundant leading `artifacts/` and prefixes the
run's folder. The path it returns is the one the agent puts in its output, so the worker's
`save_output`, the API's `/files` mount and later `get` / `signed_url` calls all see the scoped
path — no agent and no adapter changes.

Reads (`get`, `signed_url`, and a publisher's upload) are allowed for the run's own user and for
paths written before this scoping existed; a path inside another user's folder is refused.
"""

from __future__ import annotations

import dataclasses
from pathlib import PurePosixPath
from uuid import UUID

from contracts.errors import NonRetryableAgentError
from contracts.ports import Ports, PublishMetadata, PublishPort, PublishResult, StoragePort

# Agents name their files `artifacts/...`; the root/bucket already is `artifacts`.
LEGACY_ROOT = "artifacts"


def _is_uuid(segment: str) -> bool:
    try:
        UUID(segment)
    except ValueError:
        return False
    return True


class RunScopedStorage:
    """A StoragePort that files every write under `{user_id}/{run_id}/`."""

    def __init__(self, inner: StoragePort, user_id: UUID | None, run_id: UUID):
        self._inner = inner
        self._user = str(user_id) if user_id is not None else None
        self.prefix = f"{user_id}/{run_id}" if user_id is not None else str(run_id)

    def scoped(self, path: str) -> str:
        """Where a write of `path` actually lands. Idempotent for a path already in this run's folder."""
        clean = PurePosixPath(path)
        if clean.is_absolute() or ".." in clean.parts or not clean.parts:
            raise ValueError(f"invalid storage path: {path}")
        parts = clean.parts
        if "/".join(parts).startswith(self.prefix + "/"):
            return "/".join(parts)
        if parts[0] == LEGACY_ROOT and len(parts) > 1:
            parts = parts[1:]
        return "/".join((self.prefix, *parts))

    def check_readable(self, path: str) -> None:
        """Refuse a path inside another user's folder (a path typed into a node's configuration)."""
        first = PurePosixPath(path).parts[:1]
        if self._user is None or not first or not _is_uuid(first[0]):
            return  # written before per-run folders, or a run with no known owner
        if first[0] != self._user:
            raise NonRetryableAgentError("That file belongs to another account.", code="storage_forbidden")

    async def put(self, path: str, data: bytes, content_type: str) -> str:
        return await self._inner.put(self.scoped(path), data, content_type)

    async def get(self, path: str) -> bytes:
        self.check_readable(path)
        return await self._inner.get(path)

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        self.check_readable(path)
        return await self._inner.signed_url(path, expires_in)


class RunScopedPublisher:
    """A publisher reads the file itself, so it gets the same ownership check before it uploads."""

    def __init__(self, inner: PublishPort, storage: RunScopedStorage):
        self._inner, self._storage = inner, storage

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        self._storage.check_readable(storage_path)
        return await self._inner.publish(storage_path, meta)


def run_ports(ports: Ports, user_id: UUID | None, run_id: UUID) -> Ports:
    """The ports one run's agents see: the same adapters, with storage scoped to the run."""
    storage = RunScopedStorage(ports.storage, user_id, run_id)
    publishers = {name: RunScopedPublisher(p, storage) for name, p in ports.publishers.items()}
    return dataclasses.replace(ports, storage=storage, publishers=publishers)
