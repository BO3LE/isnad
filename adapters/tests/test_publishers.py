"""YouTubePublisher and DrivePublisher against a stand-in for Google's resumable upload (httpx
MockTransport): no request reaches Google.

What is sent, that the file comes from storage, and — since an upload can't be undone by a retry —
that a failure is retryable only while nothing can have been published. Error shapes as Google
documents them: https://developers.google.com/youtube/v3/docs/videos/insert#errors,
https://developers.google.com/workspace/drive/api/guides/handle-errors
"""

from __future__ import annotations

import json

import httpx
import pytest

from adapters._google import google_ports
from adapters.publish import _upload
from adapters.publish.drive import UPLOAD_URL as DRIVE_URL
from adapters.publish.drive import DrivePublisher
from adapters.publish.youtube import UPLOAD_URL as YOUTUBE_URL
from adapters.publish.youtube import YouTubePublisher, video_metadata
from contracts.errors import AgentError
from contracts.ports import PublishMetadata

TOKEN = "ya29.CANARY-access-token"
CREDENTIAL = {
    "token": TOKEN,
    "refresh_token": "1//CANARY-refresh",
    "client_id": "id.apps.googleusercontent.com",
    "client_secret": "GOCSPX-CANARY",
    "scopes": [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/gmail.send",
    ],
}
VIDEO_PATH = "u1/r1/videos/n1/video.mp4"
VIDEO = b"\x00\x00\x00\x18ftypmp42 not really a video"
SESSION = "https://www.googleapis.com/upload/session/abc123"
META = PublishMetadata(title="Solar in KSA", description="Two sentences.", tags=["solar", "ksa"], privacy="unlisted")


class Storage:
    """The run's storage: the only place a publisher may read the file from."""

    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = {VIDEO_PATH: VIDEO} if files is None else files
        self.reads: list[str] = []

    async def put(self, path: str, data: bytes, content_type: str) -> str:
        self.files[path] = data
        return path

    async def get(self, path: str) -> bytes:
        self.reads.append(path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        return f"http://files.test/{path}"


class Google:
    """Answers the session POST, the upload PUT and any status query from a script, and records each."""

    def __init__(self, *, open=None, put=None, status=None):
        self.answers = {"open": open, "put": put, "status": status}
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            step = "open"
        elif "content-range" in request.headers:
            step = "status"
        else:
            step = "put"
        answer = self.answers[step]
        if answer is None:
            answer = {"open": opened(), "put": httpx.Response(200, json={"id": "vid123"})}[step]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def steps(self) -> list[str]:
        return [
            "open" if r.method == "POST" else ("status" if "content-range" in r.headers else "put")
            for r in self.requests
        ]


def opened() -> httpx.Response:
    return httpx.Response(200, headers={"Location": SESSION})


def google_error(code: int, reason: str, message: str = "Google says no.") -> httpx.Response:
    return httpx.Response(
        code, json={"error": {"code": code, "message": message, "errors": [{"reason": reason, "message": message}]}}
    )


def youtube(google: Google, storage: Storage | None = None, credential=CREDENTIAL) -> YouTubePublisher:
    return YouTubePublisher(credential, storage or Storage(), transport=httpx.MockTransport(google.handle))


def drive(google: Google, storage: Storage | None = None, credential=CREDENTIAL) -> DrivePublisher:
    return DrivePublisher(credential, storage or Storage(), transport=httpx.MockTransport(google.handle))


# ---------------------------------------------------------------- YouTube: what is sent
async def test_the_video_is_read_from_storage_and_uploaded_unlisted_as_the_account():
    google, storage = Google(), Storage()

    result = await youtube(google, storage).publish(VIDEO_PATH, META)

    assert (result.remote_url, result.platform_id) == ("https://youtu.be/vid123", "vid123")
    assert storage.reads == [VIDEO_PATH]
    start, upload = google.requests
    assert str(start.url) == YOUTUBE_URL
    assert start.headers["authorization"] == f"Bearer {TOKEN}"
    assert start.headers["x-upload-content-type"] == "video/mp4"
    assert start.headers["x-upload-content-length"] == str(len(VIDEO))
    assert json.loads(start.content) == {
        "snippet": {
            "title": "Solar in KSA",
            "description": "Two sentences.",
            "tags": ["solar", "ksa"],
            "categoryId": "22",
        },
        "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
    }
    assert str(upload.url) == SESSION and upload.method == "PUT"
    assert upload.headers["authorization"] == f"Bearer {TOKEN}"
    assert upload.content == VIDEO


def test_details_are_kept_within_youtubes_limits():
    meta = PublishMetadata(
        title="<b>Solar</b> " + "x" * 80,
        description="a < b > c " + "é" * 2600,  # 2 bytes each: over YouTube's 5,000 bytes
        tags=["<solar>", "", *[f"tag{i:03}" for i in range(200)]],
        privacy="private",
    )

    sent = video_metadata(meta)

    assert sent["snippet"]["title"].startswith("bSolar/b ") and len(sent["snippet"]["title"]) <= 100
    assert "<" not in sent["snippet"]["description"] and ">" not in sent["snippet"]["description"]
    assert len(sent["snippet"]["description"].encode()) <= 5000
    assert sent["snippet"]["tags"][0] == "solar"
    assert len(",".join(sent["snippet"]["tags"])) <= 500
    assert sent["status"]["privacyStatus"] == "private"


async def test_a_connection_without_the_youtube_scope_fails_before_any_request():
    google = Google()
    credential = dict(CREDENTIAL, scopes=["https://www.googleapis.com/auth/gmail.send"])

    with pytest.raises(AgentError) as failed:
        await youtube(google, credential=credential).publish(VIDEO_PATH, META)
    assert failed.value.code == "youtube_scope" and not failed.value.retryable
    assert "lists YouTube" in failed.value.message
    assert google.requests == []


async def test_a_file_missing_from_storage_fails_before_any_request():
    google = Google()

    with pytest.raises(AgentError) as failed:
        await youtube(google, Storage(files={})).publish(VIDEO_PATH, META)
    assert failed.value.code == "publish_file_missing" and not failed.value.retryable
    assert google.requests == []


# ---------------------------------------------------------------- YouTube: refusals while opening
@pytest.mark.parametrize(
    ("answer", "code", "retryable", "says"),
    [
        (httpx.ConnectError("refused"), "youtube_unreachable", True, "Couldn't reach YouTube"),
        (httpx.ReadTimeout("slow"), "youtube_unreachable", True, "temporary network problem"),
        (httpx.Response(503), "youtube_unavailable", True, "503"),
        (google_error(429, "rateLimitExceeded"), "youtube_rate_limited", True, "limiting"),
        (google_error(403, "quotaExceeded"), "youtube_quota", False, "daily upload limit for this project"),
        (google_error(400, "uploadLimitExceeded"), "youtube_upload_limit", False, "as many videos"),
        (google_error(401, "authError"), "expired_credential", False, "Reconnect Google"),
        (google_error(401, "youtubeSignupRequired"), "youtube_no_channel", False, "no YouTube channel"),
        (google_error(403, "insufficientPermissions"), "youtube_scope", False, "lists YouTube"),
        (google_error(400, "invalidTitle", "Bad title."), "youtube_rejected", False, "Bad title."),
        (httpx.Response(200), "youtube_no_session", True, "didn't open an upload"),
    ],
    ids=[
        "unreachable",
        "timeout",
        "5xx",
        "rate-limited",
        "quota",
        "upload-limit",
        "expired",
        "no-channel",
        "scope",
        "bad-details",
        "no-session",
    ],
)
async def test_a_refusal_before_any_bytes_are_sent(answer, code, retryable, says):
    google = Google(open=answer)

    with pytest.raises(AgentError) as failed:
        await youtube(google).publish(VIDEO_PATH, META)
    assert failed.value.code == code
    assert failed.value.retryable is retryable
    assert says in failed.value.message
    assert google.steps() == ["open"]  # no bytes went out
    assert TOKEN not in failed.value.message


# ---------------------------------------------------------------- YouTube: once the bytes may have gone
async def test_a_lost_answer_after_the_upload_is_checked_and_the_finished_video_used():
    google = Google(put=httpx.ReadTimeout("answer lost"), status=httpx.Response(201, json={"id": "vid123"}))

    result = await youtube(google).publish(VIDEO_PATH, META)

    assert result.platform_id == "vid123"
    assert google.steps() == ["open", "put", "status"]  # asked, not uploaded again
    assert google.requests[2].headers["content-range"] == f"bytes */{len(VIDEO)}"
    assert google.requests[2].content == b""


@pytest.mark.parametrize("status", [httpx.Response(308), httpx.Response(404), httpx.Response(410)])
async def test_an_upload_that_never_finished_is_retryable(status):
    google = Google(put=httpx.WriteTimeout("stalled"), status=status)

    with pytest.raises(AgentError) as failed:
        await youtube(google).publish(VIDEO_PATH, META)
    assert failed.value.code == "youtube_interrupted"
    assert failed.value.retryable  # nothing was published: the next attempt opens a new session


@pytest.mark.parametrize(
    ("put", "status"),
    [
        (httpx.ReadTimeout("answer lost"), httpx.ReadTimeout("still lost")),
        (httpx.RemoteProtocolError("dropped"), httpx.Response(500)),
        (httpx.Response(503), httpx.ConnectError("gone")),
        (httpx.Response(200, json={"kind": "youtube#video"}), None),  # finished, but no id
    ],
    ids=["no-answer-twice", "status-5xx", "5xx-then-unreachable", "no-id"],
)
async def test_an_upload_that_may_have_finished_is_not_retried(put, status):
    google = Google(put=put, status=status)

    with pytest.raises(AgentError) as failed:
        await youtube(google).publish(VIDEO_PATH, META)
    assert failed.value.code == "youtube_ambiguous"
    assert not failed.value.retryable
    assert "Check YouTube Studio before running again" in failed.value.message
    assert google.steps().count("put") == 1  # the bytes went out once


async def test_a_connection_that_never_left_this_machine_is_retryable():
    google = Google(put=httpx.ConnectError("refused"))

    with pytest.raises(AgentError) as failed:
        await youtube(google).publish(VIDEO_PATH, META)
    assert failed.value.code == "youtube_unreachable" and failed.value.retryable
    assert google.steps() == ["open", "put"]


async def test_a_refused_upload_is_reported_and_not_retried():
    google = Google(put=google_error(403, "quotaExceeded"))

    with pytest.raises(AgentError) as failed:
        await youtube(google).publish(VIDEO_PATH, META)
    assert failed.value.code == "youtube_quota" and not failed.value.retryable


# ---------------------------------------------------------------- Drive
async def test_drive_saves_the_file_privately_under_the_steps_title():
    link = "https://drive.google.com/file/d/f123/view?usp=drivesdk"
    google = Google(put=httpx.Response(200, json={"id": "f123", "name": "Solar in KSA.mp4", "webViewLink": link}))
    storage = Storage()

    result = await drive(google, storage).publish(VIDEO_PATH, META)

    assert (result.remote_url, result.platform_id) == (link, "f123")
    assert storage.reads == [VIDEO_PATH]
    start, upload = google.requests
    assert str(start.url) == DRIVE_URL
    assert start.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(start.content) == {
        "name": "Solar in KSA.mp4",
        "description": "Two sentences.",
        "mimeType": "video/mp4",
    }
    assert upload.content == VIDEO
    assert all("permissions" not in str(r.url) for r in google.requests)  # nothing is shared


async def test_drive_names_are_safe_and_a_missing_link_is_built_from_the_id():
    google = Google(put=httpx.Response(200, json={"id": "f123"}))
    storage = Storage({"u1/r1/docs/article.pdf": b"%PDF-1.7"})

    result = await drive(google, storage).publish(
        "u1/r1/docs/article.pdf", PublishMetadata(title='Q3: "plan"/draft', description="", tags=[], privacy="unlisted")
    )

    assert result.remote_url == "https://drive.google.com/file/d/f123/view"
    sent = json.loads(google.requests[0].content)
    assert sent["name"] == "Q3 plan draft.pdf"
    assert sent["mimeType"] == "application/pdf"


@pytest.mark.parametrize(
    ("answer", "code", "retryable", "says"),
    [
        (google_error(403, "storageQuotaExceeded"), "drive_full", False, "The Google Drive account is full."),
        (google_error(403, "userRateLimitExceeded"), "drive_rate_limited", True, "limiting"),
        (google_error(403, "dailyLimitExceeded"), "drive_quota", False, "daily limit"),
        (google_error(403, "insufficientPermissions"), "drive_scope", False, "lists Drive"),
        (google_error(401, "authError"), "expired_credential", False, "Reconnect Google"),
        (httpx.Response(500), "drive_unavailable", True, "500"),
    ],
)
async def test_drive_refusals(answer, code, retryable, says):
    google = Google(open=answer)

    with pytest.raises(AgentError) as failed:
        await drive(google).publish(VIDEO_PATH, META)
    assert (failed.value.code, failed.value.retryable) == (code, retryable)
    assert says in failed.value.message


async def test_drive_needs_the_drive_scope():
    google = Google()
    credential = dict(CREDENTIAL, scopes=["https://www.googleapis.com/auth/youtube.upload"])

    with pytest.raises(AgentError) as failed:
        await drive(google, credential=credential).publish(VIDEO_PATH, META)
    assert failed.value.code == "drive_scope"
    assert google.requests == []


async def test_drive_checks_a_lost_answer_too():
    google = Google(put=httpx.ReadTimeout("lost"), status=httpx.ReadTimeout("lost"))

    with pytest.raises(AgentError) as failed:
        await drive(google).publish(VIDEO_PATH, META)
    assert failed.value.code == "drive_ambiguous" and not failed.value.retryable
    assert "Check the account's Google Drive" in failed.value.message


# ---------------------------------------------------------------- wiring
async def test_google_ports_give_the_publishers_the_runs_storage(monkeypatch):
    sent: list[bytes] = []

    async def upload(service, *, data, **_kwargs):
        sent.append(data)
        return {"id": "x1"}

    monkeypatch.setattr(_upload, "upload", upload)
    storage = Storage()
    publishers, _email = google_ports(CREDENTIAL, storage)

    await publishers["youtube"].publish(VIDEO_PATH, META)
    await publishers["drive"].publish(VIDEO_PATH, META)

    assert sent == [VIDEO, VIDEO]
    assert storage.reads == [VIDEO_PATH, VIDEO_PATH]
