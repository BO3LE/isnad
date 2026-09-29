from __future__ import annotations

import base64
from typing import Literal

from contracts.errors import AgentError, NonRetryableAgentError

CLOUDFLARE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


class CloudflareImage:
    """ImagePort backed by Cloudflare Workers AI FLUX.1 Schnell."""

    def __init__(self, account_id: str, api_token: str, *, timeout: float = 60.0):
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_MODEL}"
        self._api_token = api_token
        self._timeout = timeout

    async def generate(self, prompt: str, *, aspect: Literal["landscape", "square"]) -> bytes:
        import httpx

        composition = "wide landscape composition" if aspect == "landscape" else "square composition"
        request_prompt = f"{prompt.rstrip()}. {composition}."[:2048]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url,
                    json={"prompt": request_prompt, "steps": 4},
                    headers={"Authorization": f"Bearer {self._api_token}"},
                )
        except httpx.HTTPError as exc:
            raise AgentError("Couldn't reach the image service.", code="image_unreachable") from exc

        if response.status_code in (401, 403):
            raise NonRetryableAgentError("The image service isn't set up correctly.", code="image_auth")
        if response.status_code == 400:
            raise NonRetryableAgentError("The image request wasn't accepted.", code="image_request")
        if response.status_code >= 400:
            raise AgentError(f"The image service returned an error ({response.status_code}).", code="image_error")

        try:
            encoded = response.json()["result"]["image"]
            if encoded.startswith("data:"):
                encoded = encoded.split(",", 1)[1]
            image = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise AgentError("The image service returned an invalid image.", code="image_response") from exc
        if not image:
            raise AgentError("The image service returned an empty image.", code="image_response")
        return image
