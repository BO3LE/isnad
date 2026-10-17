"""EmailPort over SMTP. With Mailpit (docker compose's `mailpit` service) every message is caught
locally and shown at http://localhost:8025, so a run's Email step can be tried end to end
without anything leaving the machine.

Standard library only (`smtplib`, run in a thread). The orchestrator owns retries, and an email
sent twice can't be unsent, so a failure is retryable only when the message certainly wasn't
accepted: the server couldn't be reached, or it answered 4xx ("try again later"). Once the
message has gone out and the answer is lost — a disconnect or a timeout while it is being sent —
nobody knows whether it was delivered, and the step fails without a retry, saying to check the
inbox first.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from contracts.errors import AgentError, NonRetryableAgentError

AMBIGUOUS_MESSAGE = (
    "The mail server stopped answering while the message was being sent, so it may have been delivered. "
    "Check the recipients' inbox (or Mailpit) before running again."
)


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int = 1025  # Mailpit's; 587 with starttls, or 465 with ssl, for a real server
    sender: str = "ISNAD <isnad@localhost>"
    username: str | None = None
    password: str | None = None  # a secret — never logged, never in a message
    starttls: bool = False
    ssl: bool = False
    timeout_s: float = 30.0


class SmtpEmail:
    def __init__(self, config: SmtpConfig):
        self.config = config

    async def send(self, to: list[str], subject: str, body: str) -> str:
        message = EmailMessage()
        message["From"] = self.config.sender
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=False, usegmt=True)
        domain = self.config.sender.rsplit("@", 1)[-1].strip(" >") or "localhost"
        message["Message-ID"] = make_msgid(domain=domain)
        message.set_content(body)
        await asyncio.to_thread(self._deliver, message)
        return message["Message-ID"]

    # ------------------------------------------------------------------ in the thread
    def _deliver(self, message: EmailMessage) -> None:
        cfg = self.config
        where = f"{cfg.host}:{cfg.port}"
        try:
            if cfg.ssl:
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    cfg.host, cfg.port, timeout=cfg.timeout_s, context=ssl.create_default_context()
                )
            else:
                server = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_s)
        except (OSError, smtplib.SMTPException) as exc:
            raise AgentError(f"Couldn't reach the mail server at {where}.", code="email_unreachable") from exc
        try:
            try:
                if cfg.starttls:
                    server.starttls(context=ssl.create_default_context())
                if cfg.username:
                    server.login(cfg.username, cfg.password or "")
            except smtplib.SMTPAuthenticationError as exc:
                raise NonRetryableAgentError(
                    "The mail server refused the username or password — check SMTP_USERNAME and SMTP_PASSWORD.",
                    code="email_auth",
                ) from exc
            except (OSError, smtplib.SMTPException) as exc:
                # Nothing has been sent yet: safe to try again.
                raise AgentError(
                    f"Couldn't set up a session with the mail server at {where}.", code="email_unreachable"
                ) from exc
            self._send_message(server, message)
        finally:
            # Not `with server:` — its QUIT can raise after the message was accepted, and that
            # error would reach the orchestrator as a retryable one: the email would go out twice.
            try:
                server.quit()
            except (OSError, smtplib.SMTPException):
                server.close()

    @staticmethod
    def _send_message(server: smtplib.SMTP, message: EmailMessage) -> None:
        try:
            refused = server.send_message(message)
        except smtplib.SMTPRecipientsRefused as exc:
            raise NonRetryableAgentError(
                f"The mail server refused every recipient: {', '.join(exc.recipients)}.", code="email_recipients"
            ) from exc
        except smtplib.SMTPSenderRefused as exc:
            raise NonRetryableAgentError(
                "The mail server refused the sender address — check EMAIL_FROM.", code="email_sender"
            ) from exc
        except smtplib.SMTPResponseException as exc:
            # The server answered, so it knows it didn't take the message: 4xx is "later", 5xx is "no".
            if 400 <= exc.smtp_code < 500:
                raise AgentError(
                    f"The mail server is busy ({exc.smtp_code}); nothing was sent.", code="email_busy"
                ) from exc
            raise NonRetryableAgentError(
                f"The mail server rejected the message ({exc.smtp_code}).", code="email_rejected"
            ) from exc
        except (TimeoutError, smtplib.SMTPServerDisconnected, OSError) as exc:
            raise NonRetryableAgentError(AMBIGUOUS_MESSAGE, code="email_ambiguous") from exc
        if refused:
            # Accepted for some recipients only: those were sent, so a retry would send them again.
            raise NonRetryableAgentError(
                f"Sent, except to: {', '.join(sorted(refused))} (the mail server refused them).",
                code="email_partly_sent",
            )
