from __future__ import annotations

import asyncio
import os
from pathlib import Path, PurePosixPath
from typing import Any

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import PublishMetadata, PublishResult


class YouTubePublisher:
    """Publish a locally stored video through YouTube Data API v3."""

    def __init__(
        self,
        credentials_json: dict[str, Any],
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        storage_root: str | None = None,
    ):
        self._credentials_json = credentials_json
        self._client_id = client_id or str(credentials_json.get("client_id") or "")
        self._client_secret = client_secret or str(credentials_json.get("client_secret") or "")
        self._storage_root = Path(storage_root or os.getenv("STORAGE_ROOT", "/data/artifacts")).resolve()

    async def publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        return await asyncio.to_thread(self._publish, storage_path, meta)

    def _local_path(self, storage_path: str) -> Path:
        relative = PurePosixPath(storage_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise NonRetryableAgentError("The video file path is invalid.", code="publish_file_path")
        path = (self._storage_root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(self._storage_root) or not path.is_file():
            raise NonRetryableAgentError(
                "The video file is no longer available to publish.", code="publish_file_missing"
            )
        return path

    def _publish(self, storage_path: str, meta: PublishMetadata) -> PublishResult:
        try:
            from google.auth.exceptions import RefreshError
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaFileUpload

            path = self._local_path(storage_path)
            credentials = Credentials(
                token=self._credentials_json.get("token"),
                refresh_token=self._credentials_json.get("refresh_token"),
                token_uri=str(self._credentials_json.get("token_uri") or "https://oauth2.googleapis.com/token"),
                client_id=self._client_id,
                client_secret=self._client_secret,
                scopes=self._credentials_json.get("scopes"),
            )
            response = (
                build("youtube", "v3", credentials=credentials, cache_discovery=False)
                .videos()
                .insert(
                    part="snippet,status",
                    body={
                        "snippet": {
                            "title": meta.title,
                            "description": meta.description,
                            "tags": meta.tags,
                            "categoryId": "22",
                        },
                        "status": {"privacyStatus": meta.privacy},
                    },
                    media_body=MediaFileUpload(str(path), mimetype="video/mp4", resumable=True),
                )
                .execute()
            )
            video_id = response.get("id")
            if not video_id:
                raise AgentError("YouTube did not return a video ID.", code="publish_response")
            return PublishResult(remote_url=f"https://www.youtube.com/watch?v={video_id}", platform_id=video_id)
        except NonRetryableAgentError:
            raise
        except RefreshError as exc:
            raise NonRetryableAgentError(
                "Your YouTube connection expired. Connect Google again and retry.", code="publish_auth"
            ) from exc
        except HttpError as exc:
            if exc.resp.status in (400, 401, 403):
                raise NonRetryableAgentError(
                    "YouTube rejected this upload or connection.", code="publish_rejected"
                ) from exc
            raise AgentError("YouTube is temporarily unavailable.", code="publish_unavailable") from exc
        except OSError as exc:
            raise AgentError("Couldn't read the video for upload.", code="publish_file_error") from exc
