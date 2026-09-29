"""GET /outputs/{id} for a file, in both storage modes (GP-plan W4).

Supabase Storage is replaced by an httpx MockTransport — no network.
"""

from __future__ import annotations

import json

import httpx
import pytest
from conftest import SETTINGS, auth_headers
from test_api import _finished_run

from api.deps import get_file_signer
from api.settings import get_settings
from api.storage import FileMissing, StorageUnavailable, SupabaseSigner

URL = "https://example.supabase.co"
KEY = "service-key"


def signer_with(handler) -> SupabaseSigner:
    signer = SupabaseSigner(URL, KEY, "artifacts")
    signer._client = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    return signer


def signing(requests: list | None = None, status: int = 200, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if body is not None or status != 200:
            return httpx.Response(status, json=body or {})
        path = request.url.path.removeprefix("/storage/v1")
        return httpx.Response(200, json={"signedURL": f"{path}?token=signed"})

    return handler


def use(client, *, signer=None, **settings):
    configured = SETTINGS.model_copy(update=settings)
    client.app.dependency_overrides[get_settings] = lambda: configured
    if signer is not None:
        client.app.dependency_overrides[get_file_signer] = lambda: signer


def _file_output_id(client, headers, sessions) -> str:
    _, run_id = _finished_run(client, headers, sessions)
    outputs = client.get(f"/runs/{run_id}/outputs", headers=headers).json()
    return next(o["id"] for o in outputs if o["kind"] == "file")


# --- Supabase mode ---------------------------------------------------------------------


def test_supabase_mode_returns_a_short_lived_signed_url(client, headers, sessions):
    requests = []
    use(client, storage_backend="supabase", download_url_expires_in=120, signer=signer_with(signing(requests)))
    output_id = _file_output_id(client, headers, sessions)

    response = client.get(f"/outputs/{output_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": output_id,
        "url": f"{URL}/storage/v1/object/sign/artifacts/runs/abc/article.md?token=signed",
        "expires_in": 120,
        "text": None,
    }
    (sent,) = requests
    assert str(sent.url) == f"{URL}/storage/v1/object/sign/artifacts/runs/abc/article.md"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(sent.content) == {"expiresIn": 120}
    assert KEY not in response.text


def test_supabase_mode_never_signs_another_users_file(client, headers, sessions):
    requests = []
    use(client, storage_backend="supabase", signer=signer_with(signing(requests)))
    output_id = _file_output_id(client, headers, sessions)

    response = client.get(f"/outputs/{output_id}", headers=auth_headers(sessions, "someone-else@gp.local"))

    assert response.status_code == 404
    assert requests == []


def test_a_file_missing_from_the_bucket_is_404(client, headers, sessions):
    body = {"statusCode": "404", "error": "not_found", "message": "Object not found"}
    use(client, storage_backend="supabase", signer=signer_with(signing(status=400, body=body)))
    output_id = _file_output_id(client, headers, sessions)

    assert client.get(f"/outputs/{output_id}", headers=headers).status_code == 404


@pytest.mark.parametrize(
    ("status", "body"),
    [(500, None), (401, {"statusCode": "401"}), (400, {"statusCode": "404", "code": "NoSuchBucket"})],
)
def test_a_storage_fault_is_503_not_a_crash(client, headers, sessions, status, body):
    use(client, storage_backend="supabase", signer=signer_with(signing(status=status, body=body)))
    output_id = _file_output_id(client, headers, sessions)

    response = client.get(f"/outputs/{output_id}", headers=headers)

    assert response.status_code == 503
    assert KEY not in response.text


def test_supabase_mode_without_a_service_key_is_503_for_files_only(client, headers, sessions):
    use(client, storage_backend="supabase", supabase_url=URL, supabase_service_key=None)
    _, run_id = _finished_run(client, headers, sessions)
    outputs = client.get(f"/runs/{run_id}/outputs", headers=headers).json()
    by_kind = {o["kind"]: o["id"] for o in outputs}

    assert client.get(f"/outputs/{by_kind['file']}", headers=headers).status_code == 503
    assert client.get(f"/outputs/{by_kind['text']}", headers=headers).status_code == 200


def test_the_signer_dependency_is_built_from_settings(client, headers, sessions):
    use(client, storage_backend="supabase", supabase_url=URL, supabase_service_key=KEY, storage_bucket="artifacts")
    configured = client.app.dependency_overrides[get_settings]()
    signer = get_file_signer(configured)
    assert isinstance(signer, SupabaseSigner)
    assert get_file_signer(SETTINGS) is None  # local mode


# --- local (development) mode ------------------------------------------------------------


def test_local_mode_serves_from_the_files_mount(client, headers, sessions):
    use(client, storage_backend="local", public_files_url="http://localhost:8000/files/")
    output_id = _file_output_id(client, headers, sessions)

    body = client.get(f"/outputs/{output_id}", headers=headers).json()

    assert body["url"] == "http://localhost:8000/files/runs/abc/article.md"
    assert body["expires_in"] == 3600


def test_local_mode_in_production_is_503_not_a_dead_link(client, headers, sessions):
    use(client, storage_backend="local", environment="production")
    output_id = _file_output_id(client, headers, sessions)

    assert client.get(f"/outputs/{output_id}", headers=headers).status_code == 503


def test_local_mode_still_hides_another_users_file(client, headers, sessions):
    output_id = _file_output_id(client, headers, sessions)
    assert client.get(f"/outputs/{output_id}", headers=auth_headers(sessions, "x@gp.local")).status_code == 404


# --- the signer on its own -----------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "/etc/passwd", "../x", "a/../../x"])
def test_the_signer_refuses_escaping_paths_without_a_request(bad):
    def handler(request):  # pragma: no cover - must not be reached
        raise AssertionError("no request expected")

    with pytest.raises(FileMissing):
        signer_with(handler).sign(bad, 60)


def test_the_signer_passes_an_absolute_link_through():
    def handler(request):
        return httpx.Response(200, json={"signedURL": "https://cdn.example/x?token=t"})

    assert signer_with(handler).sign("u/r/a.txt", 60) == "https://cdn.example/x?token=t"


def test_the_signer_maps_network_failure_and_empty_answers():
    def unreachable(request):
        raise httpx.ConnectError("down")

    with pytest.raises(StorageUnavailable):
        signer_with(unreachable).sign("u/r/a.txt", 60)
    with pytest.raises(StorageUnavailable):
        signer_with(lambda r: httpx.Response(200, content=b"<html>")).sign("u/r/a.txt", 60)


def test_the_signer_needs_credentials():
    with pytest.raises(ValueError):
        SupabaseSigner(URL, "")
