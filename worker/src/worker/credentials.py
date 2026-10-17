"""Resolve a node's credential reference into ports that act as that Google account (D-09).

A node's configuration holds `credential_id` — the id of a `credentials` row, never a token. Just
before the node runs, the worker:

1. checks the row belongs to the owner of the workflow being run (anyone else's id is "not
   connected", exactly as if it did not exist);
2. decrypts the payload (`db.crypto`);
3. refreshes the access token when it expires within five minutes, and writes the refreshed token
   back, encrypted;
4. hands the Google adapters the resolved credential through `Ports` — the agent itself never sees
   a token and never learns where it came from.

If Google answers `invalid_grant`, the row is marked `invalid_at` (the Connections screen then says
"Reconnect") and the step fails without retrying: "Your Google connection has expired or was removed."

With FAKE_ADAPTERS=true none of this runs — the worker uses the fake publishers and email.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from adapters._google import (
    MISCONFIGURED_MESSAGE,
    TOKEN_URI,
    ExpiredCredentialError,
    MissingCredentialError,
    google_ports,
    refresh_access_token,
)
from contracts.errors import NonRetryableAgentError
from contracts.manifest import AgentManifest
from contracts.ports import Ports
from contracts.run import CREDENTIAL_CONFIG_KEY, GraphNode
from db.crypto import CredentialCipher, CredentialDecryptError
from db.models import Credential, ExecutionRun, Workflow

REFRESH_MARGIN = timedelta(minutes=5)
NOT_CONNECTED = "The Google account this step uses is no longer connected. Choose another in the step's settings."


@dataclass(frozen=True)
class GoogleClient:
    client_id: str
    client_secret: str
    token_uri: str = TOKEN_URI


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class CredentialResolver:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        cipher: CredentialCipher | None,
        google: GoogleClient | None,
        *,
        http: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._sessions = sessions
        self._cipher = cipher
        self._google = google
        self._http = http
        self._now = now

    async def resolve(self, run_id: UUID, credential_ref: Any) -> dict[str, Any]:
        """Return the credential in `Credentials.from_authorized_user_info` shape, access token fresh."""
        try:
            credential_id = UUID(str(credential_ref))
        except ValueError:
            raise MissingCredentialError(NOT_CONNECTED) from None
        if self._cipher is None or self._google is None:
            raise NonRetryableAgentError(MISCONFIGURED_MESSAGE, code="google_misconfigured")

        expired = False
        with self._sessions.begin() as s:
            owner = s.scalar(
                select(Workflow.user_id)
                .join(ExecutionRun, ExecutionRun.workflow_id == Workflow.id)
                .where(ExecutionRun.id == run_id)
            )
            row = s.scalar(
                select(Credential).where(Credential.id == credential_id, Credential.user_id == owner).with_for_update()
            )
            if row is None or owner is None:
                raise MissingCredentialError(NOT_CONNECTED)
            if row.invalid_at is not None:
                raise ExpiredCredentialError()
            try:
                payload = self._cipher.decrypt(row.encrypted_payload)
            except CredentialDecryptError:
                raise NonRetryableAgentError(MISCONFIGURED_MESSAGE, code="google_misconfigured") from None

            now = self._now()
            access_expires = _utc(_parse(payload.get("access_token_expires_at")))
            if not payload.get("access_token") or access_expires is None or access_expires - REFRESH_MARGIN <= now:
                if not payload.get("refresh_token"):
                    row.invalid_at = now
                    expired = True
                else:
                    try:
                        fresh = await refresh_access_token(
                            client_id=self._google.client_id,
                            client_secret=self._google.client_secret,
                            refresh_token=payload["refresh_token"],
                            token_uri=self._google.token_uri,
                            client=self._http,
                        )
                    except ExpiredCredentialError:
                        # Record it, commit, then fail the step (raising here would roll back).
                        row.invalid_at = now
                        expired = True
                    else:
                        payload["access_token"] = fresh["access_token"]
                        payload["access_token_expires_at"] = (
                            now + timedelta(seconds=int(fresh.get("expires_in", 3600)))
                        ).isoformat()
                        if fresh.get("refresh_token"):
                            payload["refresh_token"] = fresh["refresh_token"]
                        if fresh.get("scope"):
                            payload["scope"] = fresh["scope"]
                        row.encrypted_payload = self._cipher.encrypt(payload)
                        row.updated_at = now
            scopes = list(row.scopes or [])
        if expired:
            raise ExpiredCredentialError()

        return {
            "token": payload["access_token"],
            "refresh_token": payload.get("refresh_token"),
            "token_uri": self._google.token_uri,
            "client_id": self._google.client_id,
            "client_secret": self._google.client_secret,
            "scopes": scopes or str(payload.get("scope", "")).split(),
            "expiry": payload.get("access_token_expires_at"),
        }


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class CredentialPorts:
    """The orchestrator's `ports_for`: base ports, with Google ports swapped in for a node that names an account.

    `ports` are the ones that go through a connection on this server (`adapters.factory.connection_ports`);
    `port_of` maps an agent type to the port its credential field supplies (`credential_port_of`). A node
    whose account this server doesn't use — Email over SMTP — keeps the base ports, and its account
    isn't even resolved, so an expired one can't fail a step that never needed it.
    """

    def __init__(
        self,
        base: Ports,
        resolver: CredentialResolver,
        *,
        ports: frozenset[str] = frozenset({"publishers", "email"}),
        port_of: Mapping[str, str] | None = None,
    ):
        self._base = base
        self._resolver = resolver
        self._ports = ports
        self._port_of = dict(port_of or {})

    async def __call__(self, run_id: UUID, node: GraphNode) -> Ports:
        ref = node.configuration.get(CREDENTIAL_CONFIG_KEY)
        if not ref:
            return self._base
        port = self._port_of.get(node.agent_type)
        if port is not None and port not in self._ports:
            return self._base
        credential = await self._resolver.resolve(run_id, ref)
        publishers, email = google_ports(credential, self._base.storage)
        return dataclasses.replace(
            self._base,
            publishers=publishers if "publishers" in self._ports else self._base.publishers,
            email=email if "email" in self._ports else self._base.email,
        )


def credential_port_of(catalog: Iterable[AgentManifest]) -> dict[str, str]:
    """agent type → the `Ports` field its credential field supplies (`x-port`), for the agents that have one."""
    found: dict[str, str] = {}
    for manifest in catalog:
        for prop in ((manifest.config_schema or {}).get("properties") or {}).values():
            if prop.get("x-widget") == "credential" and prop.get("x-port"):
                found[manifest.name] = prop["x-port"]
    return found


def mark_unused_connections(manifest: AgentManifest, ports: frozenset[str]) -> AgentManifest:
    """The manifest as this server publishes it: a credential field whose port doesn't go through a
    connection here gets `x-connection: "unused"`, so the API doesn't ask for an account it won't use."""
    schema = manifest.config_schema or {}
    properties = schema.get("properties") or {}
    unused = [
        name
        for name, prop in properties.items()
        if prop.get("x-widget") == "credential" and prop.get("x-port") and prop["x-port"] not in ports
    ]
    if not unused:
        return manifest
    marked = {
        name: (dict(prop, **{"x-connection": "unused"}) if name in unused else prop)
        for name, prop in properties.items()
    }
    return manifest.model_copy(update={"config_schema": dict(schema, properties=marked)})
