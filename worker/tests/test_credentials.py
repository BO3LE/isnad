"""Resolving a node's credential reference (D-09): ownership, decrypt, refresh-on-expiry, invalid_grant.

SQLite in memory and httpx.MockTransport — no PostgreSQL, no Google.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from conftest import chain
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adapters._google import ExpiredCredentialError, MissingCredentialError
from contracts.run import GraphNode, NodeStatus, RunStatus
from db.crypto import CredentialCipher
from db.models import Base, Credential, ExecutionRun, User, Workflow
from worker.credentials import CredentialPorts, CredentialResolver, GoogleClient
from worker.orchestrator import Orchestrator

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
CIPHER = CredentialCipher(Fernet.generate_key().decode())
GOOGLE = GoogleClient("client-id", "client-secret")


class TokenEndpoint:
    def __init__(self, status: int = 200, body: dict | None = None):
        self.status = status
        self.body = body or {"access_token": "ya29.refreshed", "expires_in": 3600, "token_type": "Bearer"}
        self.calls: list[bytes] = []

    def client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            self.calls.append(request.content)
            return httpx.Response(self.status, json=self.body)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture()
def sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _setup(sessions, *, access_expires_at: datetime, other_owner: bool = False):
    """A user, their workflow and run, and a credential (owned by someone else if `other_owner`)."""
    with sessions.begin() as s:
        owner, stranger = User(email="owner@gp.local"), User(email="stranger@gp.local")
        s.add_all([owner, stranger])
        s.flush()
        wf = Workflow(user_id=owner.id, name="w", graph_definition={})
        s.add(wf)
        s.flush()
        run = ExecutionRun(workflow_id=wf.id, graph_snapshot={})
        cred = Credential(
            user_id=(stranger if other_owner else owner).id,
            provider="google",
            account_email="owner@gmail.com",
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
            encrypted_payload=CIPHER.encrypt(
                {
                    "access_token": "ya29.old",
                    "refresh_token": "1//refresh",
                    "access_token_expires_at": access_expires_at.isoformat(),
                }
            ),
        )
        s.add_all([run, cred])
        s.flush()
        return run.id, cred.id


def _resolver(sessions, endpoint: TokenEndpoint) -> CredentialResolver:
    return CredentialResolver(sessions, CIPHER, GOOGLE, http=endpoint.client(), now=lambda: NOW)


async def test_a_fresh_token_is_used_as_is(sessions):
    run_id, cred_id = _setup(sessions, access_expires_at=NOW + timedelta(minutes=30))
    endpoint = TokenEndpoint()
    info = await _resolver(sessions, endpoint).resolve(run_id, str(cred_id))
    assert info["token"] == "ya29.old"
    assert info["client_id"] == "client-id"
    assert endpoint.calls == []


async def test_an_expired_token_is_refreshed_and_stored_encrypted(sessions):
    run_id, cred_id = _setup(sessions, access_expires_at=NOW - timedelta(minutes=1))
    endpoint = TokenEndpoint()
    info = await _resolver(sessions, endpoint).resolve(run_id, str(cred_id))

    assert info["token"] == "ya29.refreshed"
    assert b"refresh_token=1%2F%2Frefresh" in endpoint.calls[0]
    with sessions() as s:
        row = s.get(Credential, cred_id)
        assert b"ya29.refreshed" not in row.encrypted_payload
        stored = CIPHER.decrypt(row.encrypted_payload)
    assert stored["access_token"] == "ya29.refreshed"
    assert stored["refresh_token"] == "1//refresh"
    assert datetime.fromisoformat(stored["access_token_expires_at"]) == NOW + timedelta(hours=1)


async def test_invalid_grant_marks_the_connection_expired(sessions):
    run_id, cred_id = _setup(sessions, access_expires_at=NOW - timedelta(minutes=1))
    endpoint = TokenEndpoint(400, {"error": "invalid_grant"})
    with pytest.raises(ExpiredCredentialError) as caught:
        await _resolver(sessions, endpoint).resolve(run_id, str(cred_id))
    assert caught.value.retryable is False
    with sessions() as s:
        assert s.get(Credential, cred_id).invalid_at is not None

    # …and later runs fail straight away, without asking Google again.
    with pytest.raises(ExpiredCredentialError):
        await _resolver(sessions, endpoint).resolve(run_id, str(cred_id))
    assert len(endpoint.calls) == 1


async def test_someone_elses_credential_is_not_connected(sessions):
    run_id, cred_id = _setup(sessions, access_expires_at=NOW + timedelta(hours=1), other_owner=True)
    with pytest.raises(MissingCredentialError):
        await _resolver(sessions, TokenEndpoint()).resolve(run_id, str(cred_id))


@pytest.mark.parametrize("ref", ["not-a-uuid", str(uuid4())])
async def test_an_unknown_reference_is_not_connected(sessions, ref):
    run_id, _ = _setup(sessions, access_expires_at=NOW + timedelta(hours=1))
    with pytest.raises(MissingCredentialError):
        await _resolver(sessions, TokenEndpoint()).resolve(run_id, ref)


async def test_ports_are_swapped_only_for_a_node_that_names_an_account(sessions, ports):
    run_id, cred_id = _setup(sessions, access_expires_at=NOW + timedelta(hours=1))
    provider = CredentialPorts(ports, _resolver(sessions, TokenEndpoint()))

    plain = GraphNode(id=uuid4(), agent_type="writer")
    assert await provider(run_id, plain) is ports

    publisher = GraphNode(id=uuid4(), agent_type="publisher", configuration={"credential_id": str(cred_id)})
    swapped = await provider(run_id, publisher)
    assert swapped.llm is ports.llm
    assert type(swapped.publishers["youtube"]).__name__ == "YouTubePublisher"
    assert type(swapped.email).__name__ == "GmailEmail"
    assert json.dumps(swapped.publishers["youtube"]._credentials_json["token"]) == '"ya29.old"'


async def test_an_expired_connection_fails_the_step_once_with_a_readable_message(store, registry, ports, sleeps):
    graph = chain("shout", "reverse", config={"text": "abc"})
    graph.nodes[1].configuration["credential_id"] = str(uuid4())
    run_id = uuid4()
    store.create_run(run_id, graph)

    async def ports_for(_run_id, node):
        if node.configuration.get("credential_id"):
            raise ExpiredCredentialError()
        return ports

    status = await Orchestrator(store, registry, ports, sleep=sleeps, ports_for=ports_for).execute(run_id)

    assert status == RunStatus.FAILED
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.FAILED
    assert store.nodes[(run_id, graph.nodes[1].id)]["errors"] == [
        "Your Google connection has expired or was removed. Reconnect Google, then run again."
    ]
    assert sleeps == []  # not retried
