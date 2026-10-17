"""Keep tokens out of the API's logs.

Uvicorn's access log prints every request line with its query string, and Google sends the browser
back to /connections/google/callback with the one-time `code` and the signed `state` in it. The
filter here blanks the values of such parameters before the line is written. httpx logs each
request URL at INFO, so it is held to warnings.
"""

from __future__ import annotations

import logging
import re

SENSITIVE_PARAMS = (
    "code",
    "state",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "api_key",
    "apikey",
    "key",
    "password",
    "secret",
    "signature",
)
_SENSITIVE = re.compile(rf"(?i)([?&](?:{'|'.join(SENSITIVE_PARAMS)})=)[^&#\s\"]*")
REDACTED = "[redacted]"


def redact_query(text: str) -> str:
    """`/cb?state=abc&code=xyz&mode=popup` → `/cb?state=[redacted]&code=[redacted]&mode=popup`."""
    return _SENSITIVE.sub(rf"\1{REDACTED}", text) if "?" in text else text


class RedactQueryValues(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(redact_query(a) if isinstance(a, str) else a for a in record.args)
        elif not record.args and isinstance(record.msg, str):  # an already-formatted message
            record.msg = redact_query(record.msg)
        return True


def install_log_redaction() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactQueryValues) for f in access.filters):
        access.addFilter(RedactQueryValues())
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
