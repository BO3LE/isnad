"""The agent catalog, as published by the worker to Redis on startup.

This is how `/agents/catalog` exists without the API importing any agent.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

import redis

from contracts.manifest import AgentManifest
from contracts.queue import CATALOG_REDIS_KEY

log = logging.getLogger(__name__)


class CatalogSource(Protocol):
    def agents(self) -> list[AgentManifest] | None:
        """Return the catalog, or None when it is unavailable (no worker has started yet)."""
        ...


class RedisCatalog:
    def __init__(self, redis_url: str):
        self._redis = redis.Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)

    def agents(self) -> list[AgentManifest] | None:
        try:
            raw = self._redis.get(CATALOG_REDIS_KEY)
        except redis.RedisError:
            log.warning("agent catalog unavailable: cannot reach Redis")
            return None
        if raw is None:
            return None
        return [AgentManifest.model_validate(item) for item in json.loads(raw)]


class StaticCatalog:
    def __init__(self, manifests: list[AgentManifest] | None):
        self._manifests = manifests

    def agents(self) -> list[AgentManifest] | None:
        return self._manifests
