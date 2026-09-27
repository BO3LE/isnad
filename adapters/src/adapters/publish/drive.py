from __future__ import annotations

from contracts.ports import PublishMetadata, PublishResult


class DrivePublisher:
    """PublishPort for Google Drive. Install with `gp-adapters[google]`.

    `credentials_json`: a resolved, fresh credential (shape in `adapters._google`), built per node
    by the worker from the connection the step names. Never read from env or the graph.

    TODO(W6, Zain): upload and return a shareable link.
    """

    def __init__(self, credentials_json: dict):
        self._credentials_json = credentials_json

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        raise NotImplementedError("Google Drive publishing lands in W6")
