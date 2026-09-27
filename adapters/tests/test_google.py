"""Google token refresh and the no-connection placeholders. No network: httpx.MockTransport."""

import httpx
import pytest

from adapters._google import (
    ExpiredCredentialError,
    MissingCredentialError,
    NoGoogleEmail,
    NoGooglePublisher,
    refresh_access_token,
)
from adapters.factory import AdapterSettings, build_ports
from contracts.errors import AgentError
from contracts.ports import PublishMetadata


def _client(status: int, body: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "oauth2.googleapis.com"
        assert b"grant_type=refresh_token" in request.content
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _refresh(client):
    return await refresh_access_token(client_id="id", client_secret="secret", refresh_token="1//r", client=client)


async def test_refresh_returns_the_new_access_token():
    tokens = await _refresh(_client(200, {"access_token": "ya29.new", "expires_in": 3599}))
    assert tokens["access_token"] == "ya29.new"


async def test_invalid_grant_is_an_expired_connection_and_not_retried():
    with pytest.raises(ExpiredCredentialError) as caught:
        await _refresh(_client(400, {"error": "invalid_grant", "error_description": "Token has been revoked."}))
    assert caught.value.retryable is False
    assert caught.value.code == "expired_credential"
    assert "Google connection has expired" in caught.value.message


async def test_a_google_outage_is_retryable():
    with pytest.raises(AgentError) as caught:
        await _refresh(_client(503, {"error": "backendError"}))
    assert caught.value.retryable is True


async def test_real_mode_without_a_connection_says_so():
    with pytest.raises(MissingCredentialError) as caught:
        await NoGooglePublisher().publish("a.mp4", PublishMetadata(title="t"))
    assert caught.value.retryable is False
    with pytest.raises(MissingCredentialError):
        await NoGoogleEmail().send(["a@b.co"], "s", "b")


def test_real_mode_ports_use_the_placeholders(tmp_path):
    ports = build_ports(AdapterSettings(fake=False, storage_root=str(tmp_path)))
    assert isinstance(ports.email, NoGoogleEmail)
    assert all(isinstance(p, NoGooglePublisher) for p in ports.publishers.values())
