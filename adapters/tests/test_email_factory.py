"""Which email real mode uses (EMAIL_TRANSPORT), and which ports go through a step's Google account."""

from __future__ import annotations

import pytest

from adapters._google import NoGoogleEmail
from adapters.email.fake import FakeEmail
from adapters.email.smtp import SmtpEmail
from adapters.factory import AdapterSettings, MisconfiguredEmail, build_email, build_ports, connection_ports
from contracts.errors import AgentError


def real(**email) -> AdapterSettings:
    return AdapterSettings(fake=False, storage_root="/tmp/gp-test", llm_model="m", **email)


def test_fake_mode_never_sends(tmp_path):
    settings = AdapterSettings(fake=True, storage_root=str(tmp_path), email_transport="smtp", smtp_host="mailpit")
    assert isinstance(build_ports(settings).email, FakeEmail)
    assert connection_ports(settings) == frozenset()


def test_gmail_is_the_default_and_goes_through_the_steps_account():
    assert isinstance(build_email(real()), NoGoogleEmail)  # swapped per step for the account it names
    assert connection_ports(real()) == {"publishers", "email"}


def test_smtp_sends_through_this_server_and_no_account_is_used():
    settings = real(email_transport="smtp", smtp_host="mailpit", smtp_port=1025, email_from="ISNAD <a@b.c>")

    email = build_ports(settings).email
    assert isinstance(email, SmtpEmail)
    assert (email.config.host, email.config.port, email.config.sender) == ("mailpit", 1025, "ISNAD <a@b.c>")
    assert connection_ports(settings) == {"publishers"}  # publishing still acts as the person's account


@pytest.mark.parametrize(
    ("settings", "fragment"),
    [
        ({"email_transport": "smtp"}, "needs SMTP_HOST"),
        ({"email_transport": "smtp", "smtp_host": "h", "smtp_starttls": True, "smtp_ssl": True}, "not both"),
        ({"email_transport": "carrier-pigeon"}, "isn't one of gmail, smtp"),
    ],
    ids=["no-host", "both-tls-modes", "unknown"],
)
async def test_email_that_cant_work_fails_the_step_before_sending(settings, fragment):
    email = build_email(real(**settings))

    assert isinstance(email, MisconfiguredEmail) and fragment in email.message
    with pytest.raises(AgentError) as caught:
        await email.send(["a@example.org"], "s", "b")
    assert (caught.value.code, caught.value.retryable) == ("email_misconfigured", False)
