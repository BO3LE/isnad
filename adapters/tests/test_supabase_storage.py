"""SupabaseStorage against a mocked HTTP layer.

The request handler stands in for the Supabase Storage REST API; the shapes it returns
(including the 400-wrapping-a-real-statusCode error body) were confirmed against a live
Supabase project.
"""

import json

import httpx
import pytest

from adapters.storage.supabase import SupabaseStorage
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import StoragePort

URL = "https://example.supabase.co"
KEY = "service-key"
PATH = "artifacts/u/r/a.txt"


def storage_with(handler, **kwargs) -> SupabaseStorage:
    """A SupabaseStorage whose httpx client is wired to `handler` instead of the network."""
    store = SupabaseStorage(URL, KEY, "artifacts", **kwargs)
    store._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return store


def test_satisfies_the_storage_protocol():
    assert isinstance(SupabaseStorage(URL, KEY), StoragePort)


async def test_put_uploads_to_the_object_endpoint_and_returns_the_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["auth"] = request.headers["authorization"]
        seen["type"] = request.headers["content-type"]
        seen["upsert"] = request.headers.get("x-upsert")
        seen["body"] = request.content
        return httpx.Response(200, json={"Key": f"artifacts/{PATH}"})

    assert await storage_with(handler).put(PATH, b"hi", "text/plain") == PATH
    assert seen["method"] == "POST"
    assert seen["url"] == f"{URL}/storage/v1/object/artifacts/{PATH}"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["type"] == "text/plain"
    assert seen["upsert"] == "true"
    assert seen["body"] == b"hi"


async def test_get_returns_the_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{URL}/storage/v1/object/artifacts/{PATH}"
        return httpx.Response(200, content=b"hi")

    assert await storage_with(handler).get(PATH) == b"hi"


async def test_signed_url_makes_the_relative_link_absolute():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{URL}/storage/v1/object/sign/artifacts/{PATH}"
        assert json.loads(request.read()) == {"expiresIn": 900}
        return httpx.Response(200, json={"signedURL": f"/object/sign/artifacts/{PATH}?token=abc"})

    link = await storage_with(handler).signed_url(PATH, 900)
    assert link == f"{URL}/storage/v1/object/sign/artifacts/{PATH}?token=abc"


async def test_signed_url_passes_an_already_absolute_link_through():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"signedURL": "https://cdn.example/x?token=abc"})

    assert await storage_with(handler).signed_url(PATH) == "https://cdn.example/x?token=abc"


async def test_paths_are_url_encoded():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"x")

    await storage_with(handler).get("artifacts/u/r/my file.txt")
    assert seen["url"].endswith("/artifacts/u/r/my%20file.txt")


@pytest.mark.parametrize("bad", ["../escape.txt", "/etc/passwd", "artifacts/../../x", ""])
async def test_refuses_paths_that_escape_the_bucket(bad):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be reached
        raise AssertionError("no request should be made")

    with pytest.raises(ValueError):
        await storage_with(handler).put(bad, b"x", "text/plain")


# --- error classification ---------------------------------------------------------


def responding(status: int, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status)
        return httpx.Response(status, json=body)

    return handler


async def test_server_error_is_retryable():
    with pytest.raises(AgentError) as caught:
        await storage_with(responding(503)).get(PATH)
    assert caught.value.retryable is True
    assert not isinstance(caught.value, NonRetryableAgentError)


async def test_rate_limit_is_retryable():
    with pytest.raises(AgentError) as caught:
        await storage_with(responding(429)).put(PATH, b"x", "text/plain")
    assert caught.value.retryable is True


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure_is_permanent(status):
    with pytest.raises(NonRetryableAgentError):
        await storage_with(responding(status)).get(PATH)


async def test_missing_object_is_permanent():
    with pytest.raises(NonRetryableAgentError) as caught:
        await storage_with(responding(404)).get(PATH)
    assert caught.value.code == "storage_not_found"


async def test_supabase_wraps_a_404_in_a_400_and_it_is_still_permanent():
    # Confirmed live: Supabase answers a missing object with HTTP 400 and the real code
    # in the body. Reading only response.status_code would still land on "permanent" here,
    # but would misfile a wrapped 5xx as permanent — hence _effective_status.
    body = {"statusCode": "404", "error": "not_found", "message": "Object not found"}
    with pytest.raises(NonRetryableAgentError) as caught:
        await storage_with(responding(400, body)).get(PATH)
    assert caught.value.code == "storage_not_found"


async def test_a_5xx_wrapped_in_a_400_is_retryable():
    body = {"statusCode": "500", "error": "InternalError", "message": "boom"}
    with pytest.raises(AgentError) as caught:
        await storage_with(responding(400, body)).get(PATH)
    assert caught.value.retryable is True


async def test_missing_bucket_is_permanent():
    body = {"statusCode": "404", "error": "Bucket not found", "code": "NoSuchBucket"}
    with pytest.raises(NonRetryableAgentError) as caught:
        await storage_with(responding(400, body)).put(PATH, b"x", "text/plain")
    assert caught.value.code == "storage_no_bucket"


async def test_too_large_is_permanent():
    with pytest.raises(NonRetryableAgentError) as caught:
        await storage_with(responding(413)).put(PATH, b"x" * 10, "text/plain")
    assert caught.value.code == "storage_too_large"


async def test_network_failure_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(AgentError) as caught:
        await storage_with(handler).get(PATH)
    assert caught.value.code == "storage_unreachable"
    assert caught.value.retryable is True


async def test_signed_url_without_a_link_is_retryable():
    with pytest.raises(AgentError) as caught:
        await storage_with(responding(200, {})).signed_url(PATH)
    assert caught.value.code == "storage_no_link"


async def test_interchangeable_with_local_storage(tmp_path):
    """The two storages must agree on return values, or swapping them changes behaviour."""
    from adapters.storage.local import LocalStorage

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hi")

    local = LocalStorage(tmp_path)
    remote = storage_with(handler)
    assert await local.put(PATH, b"hi", "text/plain") == await remote.put(PATH, b"hi", "text/plain")
    assert await local.get(PATH) == await remote.get(PATH)


def test_needs_a_url_and_a_service_key():
    with pytest.raises(ValueError):
        SupabaseStorage("", KEY)
    with pytest.raises(ValueError):
        SupabaseStorage(URL, "")


async def test_uses_the_configured_bucket_and_a_trailing_slash_is_harmless():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"signedURL": "/object/sign/other/u/r/a.txt?token=t"})

    store = SupabaseStorage(URL + "/", KEY, "other")
    store._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    link = await store.signed_url("u/r/a.txt", 60)
    assert seen["url"] == f"{URL}/storage/v1/object/sign/other/u/r/a.txt"
    assert link == f"{URL}/storage/v1/object/sign/other/u/r/a.txt?token=t"


async def test_signed_url_with_a_non_json_body_is_a_readable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    with pytest.raises(AgentError) as caught:
        await storage_with(handler).signed_url(PATH)
    assert caught.value.code == "storage_no_link"


async def test_the_service_key_never_appears_in_an_error_message():
    with pytest.raises(AgentError) as caught:
        await storage_with(responding(401)).put(PATH, b"x", "text/plain")
    assert KEY not in str(caught.value)
