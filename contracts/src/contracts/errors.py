"""Errors agents and adapters raise. The worker reads `retryable` to decide whether to retry."""

from __future__ import annotations


class AgentError(Exception):
    """A failure the user should see. `message` must be readable — no stack traces."""

    retryable: bool = True

    def __init__(self, message: str, *, code: str = "agent_error", retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        if retryable is not None:
            self.retryable = retryable


class NonRetryableAgentError(AgentError):
    """Retrying cannot help: bad configuration, revoked credential, file too large."""

    retryable = False
