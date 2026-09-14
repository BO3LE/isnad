from __future__ import annotations

from contracts.ports import PublishMetadata, PublishResult


class YouTubePublisher:
    """PublishPort for YouTube Data API v3. Install with `gp-adapters[google]`.

    TODO(W6, Zain): resumable upload with title, description, tags and privacy;
    map quotaExceeded / uploadLimitExceeded / invalid_grant to readable AgentErrors
    (see DESIGN-SYSTEM.md §23.5).
    """

    def __init__(self, credentials_json: dict):
        self._credentials_json = credentials_json

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        raise NotImplementedError("YouTube publishing lands in W6")
