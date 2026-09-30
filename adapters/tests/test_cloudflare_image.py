import asyncio
import base64

import httpx
import pytest

from adapters.image.cloudflare import CLOUDFLARE_MODEL, CloudflareImage


def test_cloudflare_image_uses_workers_ai_and_decodes_the_image(monkeypatch):
    captured: dict[str, object] = {}
    jpeg = b"\xff\xd8\xff\xe0generated-image"

    async def post(self, url, *, json, headers):
        captured.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"success": True, "result": {"image": base64.b64encode(jpeg).decode()}})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    image = asyncio.run(CloudflareImage("account-1", "token-1").generate("A lighthouse", aspect="landscape"))

    assert image == jpeg
    assert captured == {
        "url": f"https://api.cloudflare.com/client/v4/accounts/account-1/ai/run/{CLOUDFLARE_MODEL}",
        "json": {"prompt": "A lighthouse. wide landscape composition.", "steps": 4},
        "headers": {"Authorization": "Bearer token-1"},
    }


@pytest.mark.parametrize(
    "status_code, error_type", [(401, "NonRetryableAgentError"), (400, "NonRetryableAgentError"), (429, "AgentError")]
)
def test_cloudflare_image_classifies_service_errors(monkeypatch, status_code, error_type):
    async def post(self, url, *, json, headers):
        return httpx.Response(status_code)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(CloudflareImage("account-1", "token-1").generate("A lighthouse", aspect="square"))

    assert type(exc_info.value).__name__ == error_type
