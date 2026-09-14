from __future__ import annotations

from contracts.ports import PublishMetadata, PublishResult


class DrivePublisher:
    """PublishPort for Google Drive. Install with `gp-adapters[google]`.

    TODO(W6, Zain): upload and return a shareable link.
    """

    def __init__(self, credentials_json: dict):
        self._credentials_json = credentials_json

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        raise NotImplementedError("Google Drive publishing lands in W6")
