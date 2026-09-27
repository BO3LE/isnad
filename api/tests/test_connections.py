"""Connections (D-09): Google OAuth start/callback, list, disconnect, and the no-secrets-in-graphs rule.

Google is never called: its token and revoke endpoints are an httpx.MockTransport.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import jwt
import pytest
from conftest import CATALOG, SETTINGS, auth_headers, graph
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api import google_oauth
from api.catalog import StaticCatalog
from api.deps import get_catalog, get_enqueuer, get_session
from api.main import create_app
from api.routers.connections import get_google_transport
from api.settings import get_settings
from contracts.agent_io import PublishConfig
from contracts.manifest import AgentManifest
from db.crypto import CredentialCipher
from db.models import Credential, User

KEY = Fernet.generate_key().decode()
GOOGLE = SETTINGS.model_copy(
    update={
        "google_client_id": "client-id.apps.googleusercontent.com",
        "google_client_secret": "GOCSPX-test-secret",
        "credentials_encryption_key": KEY,
        "frontend_url": "http://localhost:5173",
    }
)
ACCESS = "ya29.a0-ACCESS-TOKEN-never-shown-anywhere"
REFRESH = "1//0REFRESH-TOKEN-never-shown-anywhere"
SCOPE = " ".join(google_oauth.SCOPES)

PUBLISHER = AgentManifest(
    name="publisher",
    version="0.1.0",
    title="Publisher",
    description="d",
    input_type="PublishInput",
    output_type="PublishOutput",
    config_schema=PublishConfig.model_json_schema(),
)


def id_token(email: str = "Hasan.Team@gmail.com", aud: str = GOOGLE.google_client_id) -> str:
    claims = {"iss": "https://accounts.google.com", "aud": aud, "email": email, "sub": "123"}
    return jwt.encode(claims, "google-signs-this-with-rs256-not-a-shared-secret", algorithm="HS256")


class FakeGoogle:
    """Google's token and revoke endpoints."""

    def __init__(self) -> None:
        self.token_response: tuple[int, dict] = (
            200,
            {
                "access_token": ACCESS,
                "refresh_token": REFRESH,
                "expires_in": 3599,
                "scope": SCOPE,
                "token_type": "Bearer",
                "id_token": id_token(),
            },
        )
        self.revoked: list[str] = []
        self.revoke_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        if request.url.path == "/token":
            assert form["grant_type"] == ["authorization_code"]
            assert form["redirect_uri"] == [GOOGLE.google_redirect_uri]
            status, body = self.token_response
            return httpx.Response(status, json=body)
        if request.url.path == "/revoke":
            self.revoked.append(form["token"][0])
            return httpx.Response(self.revoke_status)
        raise AssertionError(f"unexpected call to {request.url}")


@pytest.fixture()
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture()
def settings():
    return GOOGLE.model_copy()


@pytest.fixture()
def client(sessions, enqueuer, google, settings):
    app = create_app(settings)

    def session_override():
        with sessions() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_enqueuer] = lambda: enqueuer
    app.dependency_overrides[get_catalog] = lambda: StaticCatalog([*CATALOG, PUBLISHER])
    app.dependency_overrides[get_google_transport] = lambda: httpx.MockTransport(google.handler)
    with TestClient(app) as test_client:
        yield test_client


def start(client, headers, mode: str = "redirect") -> str:
    response = client.post(f"/connections/google/start?mode={mode}", headers=headers)
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]


def connect(client, headers, **params) -> httpx.Response:
    state = start(client, headers)
    return client.get(
        "/connections/google/callback", params={"state": state, "code": "4/code", **params}, follow_redirects=False
    )


# ---------------------------------------------------------------- start
def test_start_asks_google_for_offline_access_and_the_three_services(client, headers):
    response = client.post("/connections/google/start", headers=headers)
    assert response.status_code == 200
    url = urlparse(response.json()["authorization_url"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.google.com"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["redirect_uri"] == GOOGLE.google_redirect_uri
    assert query["client_id"] == GOOGLE.google_client_id
    for scope in ("youtube.upload", "drive.file", "gmail.send"):
        assert f"https://www.googleapis.com/auth/{scope}" in query["scope"].split()
    # The state is bound to this user and to this browser's cookie.
    claims = jwt.decode(query["state"], SETTINGS.jwt_secret, algorithms=["HS256"], audience="isnad:google-oauth")
    assert client.cookies.get(google_oauth.NONCE_COOKIE) == claims["nonce"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_start_needs_sign_in(client):
    assert client.post("/connections/google/start").status_code == 401


def test_start_without_google_configured_is_503(client, headers, settings):
    settings.google_client_id = ""
    response = client.post("/connections/google/start", headers=headers)
    assert response.status_code == 503
    assert "aren't set up" in response.json()["detail"]


# ---------------------------------------------------------------- callback
def test_callback_stores_the_tokens_encrypted_and_returns_to_connections(client, headers, sessions):
    response = connect(client, headers)

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/settings/connections?connected=google"
    with sessions() as s:
        row = s.query(Credential).one()
        assert row.account_email == "hasan.team@gmail.com"
        assert row.provider == "google"
        assert ACCESS.encode() not in row.encrypted_payload
        assert REFRESH.encode() not in row.encrypted_payload
        assert b"ya29" not in row.encrypted_payload and b"1//" not in row.encrypted_payload
        payload = CredentialCipher(KEY).decrypt(row.encrypted_payload)
    assert payload["access_token"] == ACCESS
    assert payload["refresh_token"] == REFRESH
    assert row.expires_at is None  # a published app's refresh token has no end date


def test_a_tampered_state_is_refused_and_nothing_is_stored(client, headers, sessions):
    state = start(client, headers)
    header, body, signature = state.split(".")
    forged = f"{header}.{body}.{'A' * len(signature)}"
    response = client.get(
        "/connections/google/callback", params={"state": forged, "code": "4/code"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("/settings/connections?error=google_state")
    with sessions() as s:
        assert s.query(Credential).count() == 0


def test_a_state_signed_with_another_secret_is_refused(client, headers, sessions):
    start(client, headers)  # sets this browser's cookie
    nonce = client.cookies.get(google_oauth.NONCE_COOKIE)
    other = SETTINGS.model_copy(update={"jwt_secret": "x" * 40})
    forged = google_oauth.make_state(other, uuid4(), nonce, "redirect")
    response = client.get("/connections/google/callback", params={"state": forged, "code": "c"}, follow_redirects=False)
    assert "error=google_state" in response.headers["location"]


def test_a_consent_link_opened_in_another_browser_is_refused(client, headers, sessions):
    state = start(client, headers)
    client.cookies.clear()  # someone else's browser: no cookie from /start
    response = client.get("/connections/google/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert "error=google_state" in response.headers["location"]
    with sessions() as s:
        assert s.query(Credential).count() == 0


def test_pressing_cancel_on_google_comes_back_as_denied(client, headers):
    state = start(client, headers)
    response = client.get(
        "/connections/google/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("?error=google_denied")


def test_a_failed_code_exchange_is_reported(client, headers, google, sessions):
    google.token_response = (400, {"error": "invalid_grant"})
    response = connect(client, headers)
    assert response.headers["location"].endswith("?error=google_failed")
    with sessions() as s:
        assert s.query(Credential).count() == 0


def test_an_id_token_for_another_client_is_refused(client, headers, google):
    google.token_response[1]["id_token"] = id_token(aud="someone-else")
    assert connect(client, headers).headers["location"].endswith("?error=google_failed")


def test_popup_mode_tells_the_opener_and_closes(client, headers):
    state = start(client, headers, mode="popup")
    response = client.get("/connections/google/callback", params={"state": state, "code": "c"})
    assert response.status_code == 200
    assert "postMessage" in response.text and "isnad:google-connection" in response.text
    assert '"http://localhost:5173"' in response.text  # only the app's origin receives it
    assert ACCESS not in response.text


def test_reconnecting_the_same_account_keeps_its_id(client, headers, google, sessions):
    connect(client, headers)
    with sessions() as s:
        first = s.query(Credential).one()
        s.query(Credential).update({"invalid_at": datetime.now(UTC)})
        s.commit()

    # Google may omit the refresh token on a reconnect; the one already stored is kept.
    google.token_response = (200, {**google.token_response[1], "access_token": "ya29.second"})
    del google.token_response[1]["refresh_token"]
    connect(client, headers)

    with sessions() as s:
        row = s.query(Credential).one()
        payload = CredentialCipher(KEY).decrypt(row.encrypted_payload)
    assert row.id == first.id
    assert row.invalid_at is None
    assert payload["access_token"] == "ya29.second"
    assert payload["refresh_token"] == REFRESH


def test_a_testing_mode_app_gets_an_end_date(client, headers, google):
    google.token_response[1]["refresh_token_expires_in"] = 7 * 24 * 3600
    connect(client, headers)
    [conn] = client.get("/connections", headers=headers).json()
    assert conn["status"] == "expiring"
    assert conn["expires_at"] is not None


# ---------------------------------------------------------------- list
def test_list_shows_plain_words_and_never_a_token(client, headers):
    connect(client, headers)
    response = client.get("/connections", headers=headers)
    assert response.status_code == 200
    [conn] = response.json()
    assert conn["account_email"] == "hasan.team@gmail.com"
    assert conn["scopes"] == ["YouTube", "Drive", "Gmail"]
    assert conn["status"] == "connected"
    assert conn["used_by"] == 0
    assert set(conn) == {"id", "provider", "account_email", "scopes", "status", "expires_at", "created_at", "used_by"}
    for secret in (ACCESS, REFRESH, "ya29", "1//", "GOCSPX", KEY):
        assert secret not in response.text


def test_used_by_counts_workflows_that_reference_it(client, headers):
    connect(client, headers)
    [conn] = client.get("/connections", headers=headers).json()
    config = {"platform": "youtube", "credential_id": conn["id"]}
    for _ in range(2):
        body = {"name": "w", "graph": graph("publisher", configs=[config])}
        assert client.post("/workflows", json=body, headers=headers).status_code == 201
    client.post("/workflows", json={"name": "other", "graph": graph("writer")}, headers=headers)
    [conn] = client.get("/connections", headers=headers).json()
    assert conn["used_by"] == 2


def test_an_expired_connection_is_listed_as_expired(client, headers, sessions):
    connect(client, headers)
    with sessions() as s:
        s.query(Credential).update({"invalid_at": datetime.now(UTC) - timedelta(minutes=1)})
        s.commit()
    [conn] = client.get("/connections", headers=headers).json()
    assert conn["status"] == "expired"


def test_other_users_connections_are_invisible(client, headers, sessions):
    connect(client, headers)
    other = auth_headers(sessions, "someone@gp.local")
    assert client.get("/connections", headers=other).json() == []


# ---------------------------------------------------------------- disconnect
def test_disconnect_revokes_at_google_and_forgets(client, headers, google, sessions):
    connect(client, headers)
    [conn] = client.get("/connections", headers=headers).json()
    assert client.delete(f"/connections/{conn['id']}", headers=headers).status_code == 204
    assert google.revoked == [REFRESH]
    assert client.get("/connections", headers=headers).json() == []


def test_disconnect_still_forgets_when_google_is_down(client, headers, google):
    connect(client, headers)
    google.revoke_status = 503
    [conn] = client.get("/connections", headers=headers).json()
    assert client.delete(f"/connections/{conn['id']}", headers=headers).status_code == 204
    assert client.get("/connections", headers=headers).json() == []


def test_someone_elses_connection_is_404(client, headers, google, sessions):
    connect(client, headers)
    [conn] = client.get("/connections", headers=headers).json()
    other = auth_headers(sessions, "someone@gp.local")
    assert client.delete(f"/connections/{conn['id']}", headers=other).status_code == 404
    assert client.delete(f"/connections/{uuid4()}", headers=headers).status_code == 404
    assert google.revoked == []
    assert len(client.get("/connections", headers=headers).json()) == 1


# ---------------------------------------------------------------- workflows hold references only
@pytest.mark.parametrize(
    "config",
    [
        {"platform": "youtube", "credential_id": ACCESS},
        {"platform": "youtube", "title": f"my token is {REFRESH}"},
        {"platform": "youtube", "refresh_token": "anything"},
        {"platform": "youtube", "credential_id": "not-a-uuid"},
    ],
)
def test_a_graph_carrying_a_secret_is_refused(client, headers, config):
    body = {"name": "w", "graph": graph("publisher", configs=[config])}
    response = client.post("/workflows", json=body, headers=headers)
    assert response.status_code == 422
    assert "never stored in a workflow" in response.json()["detail"]

    wf = client.post("/workflows", json={"name": "w"}, headers=headers).json()
    response = client.put(
        f"/workflows/{wf['id']}", json={"graph": graph("publisher", configs=[config])}, headers=headers
    )
    assert response.status_code == 422


def _validate(client, headers, config) -> list[dict]:
    body = {"name": "w", "graph": graph("publisher", configs=[config])}
    wf = client.post("/workflows", json=body, headers=headers).json()
    return client.post(f"/workflows/{wf['id']}/validate", headers=headers).json()["issues"]


def test_with_fakes_a_missing_connection_is_only_a_warning(client, headers):
    [issue] = _validate(client, headers, {"platform": "youtube"})
    assert issue == {
        "code": "missing_credential",
        "message": "Publisher needs a Google connection.",
        "severity": "warning",
        "node_id": issue["node_id"],
        "edge_id": None,
    }


def test_with_real_adapters_a_missing_connection_blocks_the_run(client, headers, settings, enqueuer):
    settings.fake_adapters = False
    body = {"name": "w", "graph": graph("publisher", configs=[{"platform": "youtube"}])}
    wf = client.post("/workflows", json=body, headers=headers).json()
    response = client.post(f"/workflows/{wf['id']}/run", headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["issues"][0]["code"] == "missing_credential"
    assert enqueuer.runs == []


def test_a_connection_of_another_user_counts_as_missing(client, headers, sessions, settings):
    settings.fake_adapters = False
    with sessions() as s:
        stranger = User(email="stranger@gp.local")
        s.add(stranger)
        s.flush()
        row = Credential(user_id=stranger.id, provider="google", account_email="x@gmail.com", encrypted_payload=b"x")
        s.add(row)
        s.commit()
        foreign_id = str(row.id)
    [issue] = _validate(client, headers, {"platform": "youtube", "credential_id": foreign_id})
    assert issue["code"] == "missing_credential" and issue["severity"] == "error"


def test_an_expired_connection_is_reported(client, headers, sessions, settings):
    settings.fake_adapters = False
    connect(client, headers)
    with sessions() as s:
        s.query(Credential).update({"invalid_at": datetime.now(UTC)})
        s.commit()
    [conn] = client.get("/connections", headers=headers).json()
    [issue] = _validate(client, headers, {"platform": "youtube", "credential_id": conn["id"]})
    assert issue["code"] == "expired_credential"
    assert issue["message"] == "Publisher's Google connection has expired."


def test_a_valid_connection_passes(client, headers, settings):
    settings.fake_adapters = False
    connect(client, headers)
    [conn] = client.get("/connections", headers=headers).json()
    assert _validate(client, headers, {"platform": "youtube", "credential_id": conn["id"]}) == []
