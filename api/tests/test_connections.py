"""Connections (D-09): Google OAuth start/callback, list, disconnect, and the no-secrets-in-graphs rule.

Google is never called: its token and revoke endpoints are an httpx.MockTransport.
"""

from __future__ import annotations

import logging
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
from contracts.agent_io import EmailConfig, PublishConfig
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
    """Google's token and revoke endpoints. Unless a test says otherwise, the person grants every
    scope the last consent asked for (`asked`)."""

    def __init__(self) -> None:
        self.token_response: tuple[int, dict] = (
            200,
            {
                "access_token": ACCESS,
                "refresh_token": REFRESH,
                "expires_in": 3599,
                "token_type": "Bearer",
                "id_token": id_token(),
            },
        )
        self.asked = ""
        self.revoked: list[str] = []
        self.revoke_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        if request.url.path == "/token":
            assert form["grant_type"] == ["authorization_code"]
            assert form["redirect_uri"] == [GOOGLE.google_redirect_uri]
            status, body = self.token_response
            return httpx.Response(status, json={"scope": self.asked, **body} if status == 200 else body)
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
        test_client.google = google  # type: ignore[attr-defined]
        yield test_client


def start(client, headers, mode: str = "redirect", access: str = "youtube") -> str:
    response = client.post(f"/connections/google/start?access={access}&mode={mode}", headers=headers)
    assert response.status_code == 200, response.text
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    client.google.asked = query["scope"][0]
    return query["state"][0]


def connect(client, headers, access: str = "youtube", **params) -> httpx.Response:
    state = start(client, headers, access=access)
    return client.get(
        "/connections/google/callback", params={"state": state, "code": "4/code", **params}, follow_redirects=False
    )


YOUTUBE = "https://www.googleapis.com/auth/youtube.upload"
DRIVE = "https://www.googleapis.com/auth/drive.file"
GMAIL = "https://www.googleapis.com/auth/gmail.send"


# ---------------------------------------------------------------- start
@pytest.mark.parametrize(
    ("access", "services"), [("youtube", {YOUTUBE}), ("drive_gmail", {DRIVE, GMAIL})], ids=["youtube", "drive_gmail"]
)
def test_start_asks_google_for_offline_access_to_one_access(client, headers, access, services):
    response = client.post(f"/connections/google/start?access={access}", headers=headers)
    assert response.status_code == 200
    url = urlparse(response.json()["authorization_url"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.google.com"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["redirect_uri"] == GOOGLE.google_redirect_uri
    assert query["client_id"] == GOOGLE.google_client_id
    assert set(query["scope"].split()) == {"openid", "https://www.googleapis.com/auth/userinfo.email", *services}
    # The state is bound to this user, to what was asked for and to this browser's cookie.
    claims = jwt.decode(query["state"], SETTINGS.jwt_secret, algorithms=["HS256"], audience="isnad:google-oauth")
    assert claims["access"] == access
    assert client.cookies.get(google_oauth.NONCE_COOKIE) == claims["nonce"]
    assert "httponly" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize("access", list(google_oauth.ACCESS))
def test_start_never_asks_for_youtube_together_with_drive(client, headers, access):
    """Google refuses that consent: "This request contains scopes that cannot be requested together".
    Nor may it fold the account's other access in (include_granted_scopes)."""
    response = client.post(f"/connections/google/start?access={access}", headers=headers)
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert not {YOUTUBE, DRIVE} <= set(query["scope"][0].split())
    assert "include_granted_scopes" not in query


def test_start_says_which_access(client, headers):
    assert client.post("/connections/google/start", headers=headers).status_code == 422
    assert client.post("/connections/google/start?access=everything", headers=headers).status_code == 422


def test_start_needs_sign_in(client):
    assert client.post("/connections/google/start?access=youtube").status_code == 401


def test_start_without_google_configured_is_503(client, headers, settings):
    settings.google_client_id = ""
    response = client.post("/connections/google/start?access=youtube", headers=headers)
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
    forged = google_oauth.make_state(other, uuid4(), nonce, "redirect", "youtube")
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


@pytest.mark.parametrize("access", list(google_oauth.ACCESS))
def test_a_consent_that_grants_none_of_what_it_asked_for_is_refused(client, headers, google, sessions, access):
    # Google's consent screen lets the person untick each service; only who they are is left.
    google.token_response[1]["scope"] = "openid https://www.googleapis.com/auth/userinfo.email"
    response = connect(client, headers, access=access)
    assert response.headers["location"].endswith("?error=google_scopes")
    with sessions() as s:
        assert s.query(Credential).count() == 0


def test_a_consent_that_grants_only_some_services_is_kept_with_what_it_grants(client, headers, google, sessions):
    google.token_response[1]["scope"] = f"openid {GMAIL}"
    assert connect(client, headers, access="drive_gmail").headers["location"].endswith("?connected=google")
    listed = client.get("/connections", headers=headers).json()
    assert [(c["access"], c["scopes"]) for c in listed] == [("drive_gmail", ["Gmail"])]


def test_connecting_writes_no_token_code_or_state_to_the_logs(client, headers, google, caplog):
    caplog.set_level(logging.DEBUG)
    state = start(client, headers)
    code = "4/0CANARY-authorization-code"
    response = client.get("/connections/google/callback", params={"state": state, "code": code}, follow_redirects=False)
    assert response.headers["location"].endswith("?connected=google")
    # Everything the server logged. The test client's own request log (httpx2) is the browser's side.
    logged = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx2"))
    assert "google account connected" in logged
    for secret in (
        state,
        code,
        ACCESS,
        REFRESH,
        google.token_response[1]["id_token"],
        GOOGLE.google_client_secret,
        KEY,
    ):
        assert secret not in logged


def test_popup_mode_tells_the_opener_and_closes(client, headers):
    state = start(client, headers, mode="popup")
    response = client.get("/connections/google/callback", params={"state": state, "code": "c"})
    assert response.status_code == 200
    assert "postMessage" in response.text and "isnad:google-connection" in response.text
    assert '"http://localhost:5173"' in response.text  # only the app's origin receives it
    # Cut off from its opener (Google's COOP), it goes to the app's page, which tells the waiting tab.
    assert '"http://localhost:5173/settings/connections?connected=google&popup=1"' in response.text
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


def test_youtube_and_drive_gmail_are_two_connections_of_one_account(client, headers, google, sessions):
    connect(client, headers, access="youtube")
    google.token_response[1].update(access_token="ya29.drive", refresh_token="1//0drive-refresh")
    connect(client, headers, access="drive_gmail")

    listed = client.get("/connections", headers=headers).json()
    assert sorted((c["account_email"], c["access"], c["scopes"]) for c in listed) == [
        ("hasan.team@gmail.com", "drive_gmail", ["Drive", "Gmail"]),
        ("hasan.team@gmail.com", "youtube", ["YouTube"]),
    ]
    with sessions() as s:
        tokens = {
            row.access: CredentialCipher(KEY).decrypt(row.encrypted_payload)["refresh_token"]
            for row in s.query(Credential)
        }
    assert tokens == {"youtube": REFRESH, "drive_gmail": "1//0drive-refresh"}

    # Reconnecting YouTube renews only YouTube's connection, in place.
    google.token_response[1].update(access_token="ya29.youtube-again", refresh_token="1//0youtube-again")
    connect(client, headers, access="youtube")
    again = client.get("/connections", headers=headers).json()
    assert sorted(c["id"] for c in again) == sorted(c["id"] for c in listed)
    with sessions() as s:
        row = s.query(Credential).filter_by(access="drive_gmail").one()
        assert CredentialCipher(KEY).decrypt(row.encrypted_payload)["refresh_token"] == "1//0drive-refresh"


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
    assert conn["access"] == "youtube"
    assert conn["scopes"] == ["YouTube"]
    assert conn["status"] == "connected"
    assert conn["used_by"] == 0
    assert set(conn) == {
        "id",
        "provider",
        "account_email",
        "access",
        "scopes",
        "status",
        "expires_at",
        "created_at",
        "used_by",
    }
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


def test_disconnect_forgets_every_connection_of_that_google_account(client, headers, google):
    """Google may end an account's other connections when one is revoked, so none is left behind."""
    connect(client, headers, access="youtube")
    google.token_response[1]["refresh_token"] = "1//0drive-refresh"
    connect(client, headers, access="drive_gmail")
    google.token_response[1].update(id_token=id_token("other@gmail.com"), refresh_token="1//0other-refresh")
    connect(client, headers, access="youtube")
    youtube = next(
        c for c in client.get("/connections", headers=headers).json() if c["account_email"] != "other@gmail.com"
    )

    assert client.delete(f"/connections/{youtube['id']}", headers=headers).status_code == 204
    assert sorted(google.revoked) == sorted([REFRESH, "1//0drive-refresh"])
    assert [c["account_email"] for c in client.get("/connections", headers=headers).json()] == ["other@gmail.com"]


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


# ---------------------------------------------------------------- an account this server doesn't use


def _email_manifest(schema: dict) -> AgentManifest:
    return AgentManifest(
        name="email",
        version="0.1.0",
        title="Email",
        description="d",
        input_type="EmailInput",
        output_type="EmailOutput",
        config_schema=schema,
    )


def _email_issues(client, headers, schema: dict) -> list[dict]:
    client.app.dependency_overrides[get_catalog] = lambda: StaticCatalog([*CATALOG, PUBLISHER, _email_manifest(schema)])
    body = {"name": "w", "graph": graph("email", configs=[{"recipients": ["a@example.org"]}])}
    wf = client.post("/workflows", json=body, headers=headers).json()
    return client.post(f"/workflows/{wf['id']}/validate", headers=headers).json()["issues"]


def test_with_real_adapters_and_gmail_an_email_step_needs_a_connection(client, headers, settings):
    settings.fake_adapters = False
    [issue] = _email_issues(client, headers, EmailConfig.model_json_schema())
    assert (issue["code"], issue["severity"]) == ("missing_credential", "error")


def test_an_account_the_worker_publishes_as_unused_is_not_asked_for(client, headers, settings):
    """Email over SMTP (Mailpit): the worker marks the field, and the run isn't blocked for want of Google."""
    settings.fake_adapters = False
    schema = EmailConfig.model_json_schema()
    schema["properties"]["credential_id"]["x-connection"] = "unused"
    assert _email_issues(client, headers, schema) == []
