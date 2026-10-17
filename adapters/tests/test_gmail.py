"""GmailEmail against a stand-in for the Gmail API (httpx MockTransport): no request reaches Google.

What is sent, and — since an email can't be unsent — that a failure is retried only when Gmail
certainly didn't take the message. Error shapes as Google documents them:
https://developers.google.com/workspace/gmail/api/guides/handle-errors
"""

from __future__ import annotations

import base64
import json
from email import message_from_bytes

import httpx
import pytest

from adapters._google import ExpiredCredentialError
from adapters.email.gmail import SEND_URL, GmailEmail
from contracts.errors import AgentError

TOKEN = "ya29.CANARY-access-token"
CREDENTIAL = {
    "token": TOKEN,
    "refresh_token": "1//CANARY-refresh",
    "client_id": "id.apps.googleusercontent.com",
    "client_secret": "GOCSPX-CANARY",
    "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/youtube.upload"],
}


def _gmail(handler, credential=CREDENTIAL) -> GmailEmail:
    return GmailEmail(credential, timeout=5, transport=httpx.MockTransport(handler))


def _answer(status: int, body: object):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=body)

    handler.requests = requests
    return handler


def _google_error(code: int, reason: str, message: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "errors": [{"domain": "usageLimits", "reason": reason, "message": message}],
        }
    }


async def test_the_message_is_sent_as_the_account_and_gmails_id_is_returned():
    handler = _answer(200, {"id": "18c0ffee", "threadId": "18c0ffee", "labelIds": ["SENT"]})

    message_id = await _gmail(handler).send(["a@example.org", "b@example.org"], "Solar in KSA", "Read it here.")

    assert message_id == "18c0ffee"
    (request,) = handler.requests
    assert (request.method, str(request.url)) == ("POST", SEND_URL)
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    sent = message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]))
    assert sent["To"] == "a@example.org, b@example.org"
    assert sent["Subject"] == "Solar in KSA"
    assert sent["From"] is None  # Gmail sends as the connected account
    assert sent.get_payload(decode=True).decode().strip() == "Read it here."


async def test_a_connection_without_a_sending_scope_sends_nothing():
    handler = _answer(200, {"id": "x"})
    only_youtube = dict(CREDENTIAL, scopes=["https://www.googleapis.com/auth/youtube.upload"])

    with pytest.raises(AgentError) as caught:
        await _gmail(handler, only_youtube).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("gmail_scope", False)
    assert handler.requests == []


@pytest.mark.parametrize(
    ("status", "body", "code", "retryable"),
    [
        (403, _google_error(403, "rateLimitExceeded", "Rate Limit Exceeded"), "gmail_rate_limited", True),
        (403, _google_error(403, "userRateLimitExceeded", "User Rate Limit Exceeded"), "gmail_rate_limited", True),
        (
            429,
            {"error": {"code": 429, "message": "Too many requests: User-rate limit exceeded (Mail sending)"}},
            "gmail_rate_limited",
            True,
        ),
        (403, _google_error(403, "dailyLimitExceeded", "Daily Limit Exceeded"), "gmail_quota", False),
        (
            403,
            _google_error(403, "domainPolicy", "The domain administrators have disabled Gmail apps."),
            "gmail_domain_policy",
            False,
        ),
        (
            403,
            _google_error(403, "insufficientPermissions", "Request had insufficient authentication scopes."),
            "gmail_scope",
            False,
        ),
        (400, _google_error(400, "badRequest", "Invalid To header"), "gmail_rejected", False),
        (500, _google_error(500, "backendError", "Backend Error"), "gmail_ambiguous", False),
        (503, {"error": {"code": 503, "message": "Service unavailable"}}, "gmail_ambiguous", False),
    ],
    ids=["rate", "user-rate", "429", "daily-limit", "domain-policy", "scope", "bad-request", "500", "503"],
)
async def test_each_error_says_whether_a_retry_could_send_it_twice(status, body, code, retryable):
    with pytest.raises(AgentError) as caught:
        await _gmail(_answer(status, body)).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert TOKEN not in caught.value.message


async def test_a_bad_request_says_what_gmail_objected_to():
    with pytest.raises(AgentError) as caught:
        await _gmail(_answer(400, _google_error(400, "badRequest", "Invalid To header"))).send(["x"], "s", "b")
    assert "Invalid To header" in caught.value.message


async def test_a_revoked_token_asks_to_reconnect():
    with pytest.raises(ExpiredCredentialError):
        await _gmail(_answer(401, _google_error(401, "authError", "Invalid Credentials"))).send(
            ["a@example.org"], "s", "b"
        )


async def test_gmail_unreachable_is_retryable_since_nothing_left():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AgentError) as caught:
        await _gmail(handler).send(["a@example.org"], "s", "b")
    assert (caught.value.code, caught.value.retryable) == ("gmail_unreachable", True)


@pytest.mark.parametrize(
    "lost",
    [httpx.ReadTimeout("timed out"), httpx.RemoteProtocolError("peer closed connection")],
    ids=["read-timeout", "connection-dropped"],
)
async def test_an_answer_lost_after_sending_is_not_retried(lost):
    def handler(request):
        lost.request = request
        raise lost

    with pytest.raises(AgentError) as caught:
        await _gmail(handler).send(["a@example.org"], "s", "b")
    assert (caught.value.code, caught.value.retryable) == ("gmail_ambiguous", False)
    assert "Sent folder" in caught.value.message


async def test_a_200_without_a_message_id_is_not_taken_for_a_send():
    with pytest.raises(AgentError) as caught:
        await _gmail(_answer(200, {"threadId": "t"})).send(["a@example.org"], "s", "b")
    assert (caught.value.code, caught.value.retryable) == ("gmail_ambiguous", False)
