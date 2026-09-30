from __future__ import annotations

import httpx

from contracts.errors import AgentError, NonRetryableAgentError


class MailtrapEmail:
    """Transactional Email port backed by Mailtrap's HTTPS sending API."""

    def __init__(self, token: str, from_email: str):
        self._token = token
        self._from_email = from_email

    async def send(self, to: list[str], subject: str, body: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://send.api.mailtrap.io/api/send",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={
                        "from": {"email": self._from_email},
                        "to": [{"email": address} for address in to],
                        "subject": subject,
                        "text": body,
                    },
                )
        except httpx.HTTPError as exc:
            raise AgentError("Couldn't reach the email service.", code="email_unreachable") from exc

        if response.status_code in (401, 403):
            raise NonRetryableAgentError("The email service isn't set up correctly.", code="email_auth")
        if response.status_code in (400, 404, 422):
            raise NonRetryableAgentError(
                "The email request was rejected. Check the verified sender address.", code="email_request"
            )
        if response.status_code >= 500:
            raise AgentError("The email service is temporarily unavailable.", code="email_unavailable")
        if response.status_code >= 300:
            raise AgentError(f"The email service returned an error ({response.status_code}).", code="email_error")

        data = response.json()
        message_ids = data.get("message_ids") or []
        if not message_ids:
            raise AgentError("The email service returned an invalid response.", code="email_response")
        return str(message_ids[0])
