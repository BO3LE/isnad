from __future__ import annotations


class GmailEmail:
    """EmailPort for the Gmail API, with SMTP as a fallback. Install with `gp-adapters[google]`.

    TODO(W7, Zain): send via users.messages.send; fall back to SMTP when configured.
    """

    def __init__(self, credentials_json: dict):
        self._credentials_json = credentials_json

    async def send(self, to: list[str], subject: str, body: str) -> str:
        raise NotImplementedError("Gmail sending lands in W7")
