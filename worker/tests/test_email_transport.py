"""EMAIL_TRANSPORT in the worker: the catalog it publishes, which steps resolve a Google account,
and the startup line saying where email goes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from adapters.factory import AdapterSettings, build_ports, connection_ports
from contracts.agent_io import EmailConfig, PublishConfig, ResearchConfig
from contracts.manifest import AgentManifest
from contracts.run import GraphNode
from worker import celery_app
from worker.credentials import CredentialPorts, credential_port_of, mark_unused_connections
from worker.settings import WorkerSettings

PASSWORD = "CANARY-smtp-password"


def _manifest(name: str, config) -> AgentManifest:
    return AgentManifest(
        name=name,
        version="0.1.0",
        title=name.title(),
        description="d",
        input_type="X",
        output_type="Y",
        config_schema=config.model_json_schema(),
    )


EMAIL, PUBLISHER = _manifest("email", EmailConfig), _manifest("publisher", PublishConfig)


def test_each_credential_field_names_the_port_it_supplies():
    assert credential_port_of([EMAIL, PUBLISHER, _manifest("researcher", ResearchConfig)]) == {
        "email": "email",
        "publisher": "publishers",
    }


def test_over_smtp_the_email_account_is_published_as_unused_and_the_publishers_is_not():
    used = connection_ports(AdapterSettings(fake=False, email_transport="smtp", smtp_host="mailpit"))

    email, publisher = mark_unused_connections(EMAIL, used), mark_unused_connections(PUBLISHER, used)

    assert email.config_schema["properties"]["credential_id"]["x-connection"] == "unused"
    assert "x-connection" not in publisher.config_schema["properties"]["credential_id"]
    assert publisher == PUBLISHER
    assert "x-connection" not in EMAIL.config_schema["properties"]["credential_id"]  # the original is untouched


def test_with_gmail_nothing_is_marked():
    used = connection_ports(AdapterSettings(fake=False))
    assert mark_unused_connections(EMAIL, used) == EMAIL


class Resolver:
    def __init__(self):
        self.calls = 0

    async def resolve(self, run_id, ref):
        self.calls += 1
        return {"token": "ya29.t", "refresh_token": "r", "client_id": "c", "client_secret": "s", "scopes": []}


async def test_over_smtp_an_email_step_keeps_smtp_and_its_account_is_never_resolved(tmp_path):
    settings = AdapterSettings(
        fake=False, storage_root=str(tmp_path), llm_model="m", email_transport="smtp", smtp_host="h"
    )
    base = build_ports(settings)
    resolver = Resolver()
    ports_for = CredentialPorts(
        base, resolver, ports=connection_ports(settings), port_of=credential_port_of([EMAIL, PUBLISHER])
    )
    account = {"credential_id": str(uuid4())}

    email_ports = await ports_for(uuid4(), GraphNode(id=uuid4(), agent_type="email", configuration=account))
    assert email_ports is base and resolver.calls == 0

    publisher_ports = await ports_for(uuid4(), GraphNode(id=uuid4(), agent_type="publisher", configuration=account))
    assert resolver.calls == 1
    assert type(publisher_ports.publishers["youtube"]).__name__ == "YouTubePublisher"
    assert publisher_ports.email is base.email  # still SMTP, not Gmail


def _settings(monkeypatch, **env) -> WorkerSettings:
    for name in ("EMAIL_TRANSPORT", "SMTP_HOST", "SMTP_PORT", "SMTP_PASSWORD", "FAKE_ADAPTERS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return WorkerSettings(_env_file=None)


@pytest.mark.parametrize(
    ("env", "line"),
    [
        ({"FAKE_ADAPTERS": "true"}, "Email: fake (FAKE_ADAPTERS=true)"),
        ({"FAKE_ADAPTERS": "false"}, "Email: gmail, through the Google account each Email step names"),
        (
            {"FAKE_ADAPTERS": "false", "EMAIL_TRANSPORT": "smtp", "SMTP_HOST": "mailpit", "SMTP_PASSWORD": PASSWORD},
            "Email: smtp to mailpit:1025 (Mailpit catches every message: http://localhost:8025)",
        ),
        (
            {"FAKE_ADAPTERS": "false", "EMAIL_TRANSPORT": "smtp", "SMTP_HOST": "smtp.example.org", "SMTP_PORT": "587"},
            "Email: smtp to smtp.example.org:587",
        ),
        (
            {"FAKE_ADAPTERS": "false", "EMAIL_TRANSPORT": "smtp"},
            "Email: not usable — EMAIL_TRANSPORT=smtp needs SMTP_HOST",
        ),
    ],
    ids=["fake", "gmail", "mailpit", "real-server", "no-host"],
)
def test_the_startup_line(monkeypatch, env, line):
    monkeypatch.setattr(celery_app, "settings", _settings(monkeypatch, **env))

    report = celery_app.check_email()

    assert report.startswith(line), report
    assert PASSWORD not in report


def test_the_published_catalog_marks_the_unused_account_only_in_real_smtp_mode(monkeypatch):
    class Registry:
        def catalog(self):
            return [EMAIL, PUBLISHER]

    monkeypatch.setattr(celery_app, "registry", lambda: Registry())

    def email_field(**env):
        monkeypatch.setattr(celery_app, "settings", _settings(monkeypatch, **env))
        (email, _) = celery_app.published_catalog()
        return email.config_schema["properties"]["credential_id"]

    assert email_field(FAKE_ADAPTERS="false", EMAIL_TRANSPORT="smtp", SMTP_HOST="mailpit")["x-connection"] == "unused"
    assert "x-connection" not in email_field(FAKE_ADAPTERS="false")
    assert "x-connection" not in email_field(FAKE_ADAPTERS="true", EMAIL_TRANSPORT="smtp")
