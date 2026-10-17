"""SmtpEmail against a real socket and a test SMTP server: what is sent, and when a retry is safe.

An email can't be unsent, so the rule under test is: retryable only when the message certainly
wasn't taken; once it went out and the answer was lost, fail without a retry.
"""

from __future__ import annotations

import socket
from email import message_from_bytes

import pytest

from adapters.email.smtp import SmtpConfig, SmtpEmail
from adapters.email.smtp_testing import smtp_server
from contracts.errors import AgentError

PASSWORD = "CANARY-smtp-password"


@pytest.fixture()
def server():
    with smtp_server() as s:
        yield s


def _email(server, **config) -> SmtpEmail:
    return SmtpEmail(SmtpConfig(host="127.0.0.1", port=server.port, sender="ISNAD <isnad@test.local>", **config))


async def test_the_message_is_delivered_with_its_id():
    with smtp_server() as server:
        message_id = await _email(server).send(["a@example.org", "b@example.org"], "Solar in KSA", "Read it here.")

    (raw,) = server.messages
    sent = message_from_bytes(raw)
    assert sent["From"] == "ISNAD <isnad@test.local>"
    assert sent["To"] == "a@example.org, b@example.org"
    assert sent["Subject"] == "Solar in KSA"
    assert sent["Message-ID"] == message_id and message_id.endswith("@test.local>")
    assert sent.get_payload(decode=True).decode().strip() == "Read it here."


async def test_it_logs_in_when_given_a_username(server):
    assert await _email(server, username="isnad", password=PASSWORD).send(["a@example.org"], "s", "b")


async def test_a_refused_login_is_not_retried_and_never_shows_the_password(server):
    server.mode = "auth"
    with pytest.raises(AgentError) as caught:
        await _email(server, username="isnad", password=PASSWORD).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("email_auth", False)
    assert PASSWORD not in caught.value.message
    assert server.messages == []


async def test_an_unreachable_server_is_retryable_since_nothing_was_sent():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # closed again: nothing listens there

    with pytest.raises(AgentError) as caught:
        await SmtpEmail(SmtpConfig(host="127.0.0.1", port=port, timeout_s=2)).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("email_unreachable", True)


@pytest.mark.parametrize(
    ("mode", "code", "retryable"),
    [("busy", "email_busy", True), ("reject", "email_rejected", False)],
)
async def test_an_answer_after_the_message_decides_the_retry(server, mode, code, retryable):
    server.mode = mode
    with pytest.raises(AgentError) as caught:
        await _email(server).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == (code, retryable)


async def test_a_message_whose_answer_was_lost_is_not_retried(server):
    server.mode = "drop"
    with pytest.raises(AgentError) as caught:
        await _email(server).send(["a@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("email_ambiguous", False)
    assert "may have been delivered" in caught.value.message
    assert len(server.messages) == 1  # it did reach the server


async def test_a_failing_quit_after_delivery_is_still_a_success(server):
    server.mode = "bad-quit"
    assert await _email(server).send(["a@example.org"], "s", "b")
    assert len(server.messages) == 1


async def test_every_recipient_refused_is_not_retried(server):
    server.refuse = {"a@example.org", "b@example.org"}
    with pytest.raises(AgentError) as caught:
        await _email(server).send(["a@example.org", "b@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("email_recipients", False)
    assert server.messages == []


async def test_some_recipients_refused_is_reported_and_not_retried_since_the_rest_were_sent(server):
    server.refuse = {"b@example.org"}
    with pytest.raises(AgentError) as caught:
        await _email(server).send(["a@example.org", "b@example.org"], "s", "b")

    assert (caught.value.code, caught.value.retryable) == ("email_partly_sent", False)
    assert "b@example.org" in caught.value.message
    assert len(server.messages) == 1
