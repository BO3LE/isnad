"""The "Research → PDF → Email" template with EMAIL_TRANSPORT=smtp, as with Mailpit.

Everything is real except the mail server and the model: the orchestrator, SqlRunStore on
PostgreSQL, the installed agents, the factory's `SmtpEmail` with smtplib over a real socket, and a
test SMTP server (`adapters.email.smtp_testing`) standing in for Mailpit. So this proves the email
reaches the server only after approval, says what the run wrote, and is never sent twice.
"""

from __future__ import annotations

import dataclasses
import uuid
from email import message_from_bytes

import pytest
from sqlalchemy import select

from adapters.email.smtp_testing import smtp_server
from adapters.factory import AdapterSettings, build_email
from contracts.run import ApprovalDecision, NodeStatus, RunStatus
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun
from worker.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

EMAIL = "Research → PDF → Email"


@pytest.fixture()
def mail():
    with smtp_server() as server:
        yield server


def _smtp_ports(ports, mail):
    email = build_email(AdapterSettings(fake=False, email_transport="smtp", smtp_host="127.0.0.1", smtp_port=mail.port))
    return dataclasses.replace(ports, email=email)


def _logs(db, run_id) -> list[ExecutionLog]:
    with db.sessions() as s:
        return list(
            s.scalars(
                select(ExecutionLog).where(ExecutionLog.run_id == run_id).order_by(ExecutionLog.position_order)
            ).all()
        )


def _approve(db, run_id: uuid.UUID, node_id: uuid.UUID) -> None:
    """Mirror of `POST /runs/{id}/nodes/{node}/approve` (api/routers/runs.py) up to the enqueue."""
    with db.sessions.begin() as s:
        row = s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))
        s.add(Approval(log_id=row.id, decision=ApprovalDecision.APPROVE.value, decided_by=db.demo_user_id()))
        s.get(ExecutionRun, run_id).status = RunStatus.QUEUED.value


async def test_the_email_is_sent_only_after_approval_and_carries_the_article(db, store, registry, ports, mail):
    run_id = db.start_run(db.template(EMAIL).id)
    orchestrator = Orchestrator(store, registry, _smtp_ports(ports, mail))

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert mail.messages == []  # nothing goes out before a person approves it

    _, write, email = _logs(db, run_id)
    _approve(db, run_id, email.node_id)
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    (raw,) = mail.messages
    sent = message_from_bytes(raw)
    with db.sessions() as s:
        article = s.scalar(select(AgentOutput.content_json).where(AgentOutput.log_id == write.id))
        output = s.scalar(select(AgentOutput.content_json).where(AgentOutput.log_id == email.id))
    assert sent["Subject"] == article["title"]
    assert article["summary"] in sent.get_payload(decode=True).decode()
    assert output["message_id"] == sent["Message-ID"]
    assert output["recipients"] == [a.strip() for a in sent["To"].split(",")]


async def test_a_send_whose_answer_was_lost_fails_once_and_is_never_repeated(db, store, registry, ports, mail, sleeps):
    mail.mode = "drop"
    run_id = db.start_run(db.template(EMAIL).id)
    orchestrator = Orchestrator(store, registry, _smtp_ports(ports, mail), sleep=sleeps)
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    email = _logs(db, run_id)[-1]
    _approve(db, run_id, email.node_id)

    assert await orchestrator.execute(run_id) == RunStatus.FAILED

    assert len(mail.messages) == 1 and sleeps == []  # it reached the server once; no retry
    email = _logs(db, run_id)[-1]
    assert (email.status, email.retry_count) == (NodeStatus.FAILED, 0)
    assert "Check the recipients' inbox" in email.error_message


async def test_a_busy_server_is_retried_since_nothing_was_sent(db, store, registry, ports, mail, sleeps):
    mail.mode = "busy"
    run_id = db.start_run(db.template(EMAIL).id)
    smtp_ports = _smtp_ports(ports, mail)
    assert await Orchestrator(store, registry, smtp_ports, sleep=sleeps).execute(run_id) == RunStatus.AWAITING_APPROVAL
    email = _logs(db, run_id)[-1]
    _approve(db, run_id, email.node_id)

    async def the_server_frees_up_during_the_backoff(seconds: float) -> None:
        await sleeps(seconds)
        mail.mode = "ok"

    orchestrator = Orchestrator(store, registry, smtp_ports, sleep=the_server_frees_up_during_the_backoff)
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    email = _logs(db, run_id)[-1]
    assert (email.status, email.retry_count) == (NodeStatus.SUCCESS, 1)
    assert len(sleeps) == 1
    assert len(mail.messages) == 2  # refused once with 451 ("try later"), taken the second time
