"""EmailPort for the Gmail API: `users.messages.send` as the Google account the step names (D-09).

`credentials_json` is a resolved, fresh credential (shape in `adapters._google`), built per node by
the worker from the connection the step names — never read from env or the graph. The message
goes out as that account; Gmail fills in From.

The orchestrator owns retries, and a sent email can't be unsent, so a failure is retryable only
when Gmail certainly didn't take the message: it couldn't be reached, or it refused for a rate
limit (403 rateLimitExceeded / userRateLimitExceeded, 429). A timeout once the request has gone
out, a 5xx, or a 200 without a message id can't tell whether it was sent — Google suggests retrying
5xx, but here the step fails without a retry and says to check Sent first.
Errors: https://developers.google.com/workspace/gmail/api/guides/handle-errors
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any

import httpx

from adapters._google import ExpiredCredentialError
from contracts.errors import AgentError, NonRetryableAgentError

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
# Any of these lets users.messages.send work; the connect flow asks for gmail.send.
SENDING_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://mail.google.com/",
    }
)
NO_SCOPE_MESSAGE = (
    "This Google connection isn't allowed to send email. Reconnect Google in Settings → Connections "
    "and leave Gmail ticked."
)
AMBIGUOUS_MESSAGE = (
    "Gmail didn't confirm the message, so it may have been sent. Check the account's Sent folder "
    "before running again."
)


class GmailEmail:
    """Install with `gp-adapters[google]`."""

    def __init__(self, credentials_json: dict, *, timeout: float = 30.0, transport: Any = None):
        self._credentials_json = credentials_json
        self._timeout = timeout
        self._transport = transport  # an httpx transport, for tests

    async def send(self, to: list[str], subject: str, body: str) -> str:
        scopes = set(self._credentials_json.get("scopes") or [])
        if not scopes & SENDING_SCOPES:
            raise NonRetryableAgentError(NO_SCOPE_MESSAGE, code="gmail_scope")

        message = EmailMessage()
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        headers = {"Authorization": f"Bearer {self._credentials_json['token']}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(SEND_URL, json={"raw": raw}, headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Never left this machine: safe to try again.
            raise AgentError("Couldn't reach Gmail.", code="gmail_unreachable") from exc
        except httpx.HTTPError as exc:
            # The request was on its way or out; the answer was lost.
            raise NonRetryableAgentError(AMBIGUOUS_MESSAGE, code="gmail_ambiguous") from exc

        if response.status_code == 200:
            message_id = _json(response).get("id")
            if not isinstance(message_id, str) or not message_id:
                raise NonRetryableAgentError(AMBIGUOUS_MESSAGE, code="gmail_ambiguous")
            return message_id
        raise _error(response)


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _error(response: httpx.Response) -> AgentError:
    code = response.status_code
    error = _json(response).get("error")
    error = error if isinstance(error, dict) else {}
    reasons = {e.get("reason") for e in error.get("errors") or [] if isinstance(e, dict)}
    said = str(error.get("message") or "")[:200]
    detail = f": {said}" if said else ""

    if code == 401:
        return ExpiredCredentialError()
    if code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded"}:
        return AgentError("Gmail is limiting how fast this account can send.", code="gmail_rate_limited")
    if code == 403:
        if "dailyLimitExceeded" in reasons:
            return NonRetryableAgentError(
                "Gmail's daily sending limit for this project is used up; retrying won't help until it resets.",
                code="gmail_quota",
            )
        if "domainPolicy" in reasons:
            return NonRetryableAgentError(
                "This account's domain administrators have turned off Gmail apps. Ask them, or connect "
                "another account.",
                code="gmail_domain_policy",
            )
        if "insufficientPermissions" in reasons or "scope" in said.lower():
            return NonRetryableAgentError(NO_SCOPE_MESSAGE, code="gmail_scope")
        return NonRetryableAgentError(f"Gmail refused to send it (403){detail}.", code="gmail_forbidden")
    if code >= 500:
        return NonRetryableAgentError(AMBIGUOUS_MESSAGE, code="gmail_ambiguous")
    return NonRetryableAgentError(f"Gmail refused the message ({code}){detail}.", code="gmail_rejected")
