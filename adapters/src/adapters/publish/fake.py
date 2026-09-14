from __future__ import annotations

import hashlib

from contracts.ports import PublishMetadata, PublishResult


class FakePublisher:
    def __init__(self, platform: str):
        self.platform = platform
        self.published: list[tuple[str, PublishMetadata]] = []

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        self.published.append((storage_path, meta))
        platform_id = hashlib.sha1(f"{self.platform}:{storage_path}".encode()).hexdigest()[:11]
        base = "https://youtu.be/" if self.platform == "youtube" else "https://drive.google.com/file/d/"
        return PublishResult(remote_url=base + platform_id, platform_id=platform_id)
