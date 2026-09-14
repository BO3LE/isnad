"""Agent registry — resolves `agent_type` to an agent at runtime.

Agents are discovered through the `gp.agents` entry point group declared in each agent's
pyproject.toml. Dropping a new agent folder in and installing it is all it takes (AT-12).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import entry_points

from contracts.agent import BaseAgent
from contracts.manifest import AgentManifest

ENTRY_POINT_GROUP = "gp.agents"
log = logging.getLogger(__name__)


class UnknownAgentError(LookupError):
    def __init__(self, agent_type: str):
        super().__init__(f"No agent is installed for type “{agent_type}”.")
        self.agent_type = agent_type


class Registry:
    def __init__(self, agents: Iterable[type[BaseAgent]]):
        self._agents: dict[str, type[BaseAgent]] = {}
        for agent in agents:
            name = agent.manifest.name
            if name in self._agents:
                raise ValueError(f"two agents claim the name {name!r}")
            self._agents[name] = agent

    @classmethod
    def from_entry_points(cls) -> Registry:
        found: list[type[BaseAgent]] = []
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            try:
                agent = ep.load()
            except Exception:  # one broken agent must not take the worker down
                log.exception("failed to load agent entry point %s", ep.name)
                continue
            if not (isinstance(agent, type) and issubclass(agent, BaseAgent)):
                log.error("entry point %s does not point to a BaseAgent subclass", ep.name)
                continue
            if agent.manifest.name != ep.name:
                log.error("entry point %s loads an agent whose manifest is named %s", ep.name, agent.manifest.name)
                continue
            found.append(agent)
        return cls(found)

    def get(self, agent_type: str) -> BaseAgent:
        try:
            return self._agents[agent_type]()
        except KeyError:
            raise UnknownAgentError(agent_type) from None

    def manifest(self, agent_type: str) -> AgentManifest:
        try:
            return self._agents[agent_type].manifest
        except KeyError:
            raise UnknownAgentError(agent_type) from None

    def catalog(self) -> list[AgentManifest]:
        return [agent.catalog_entry() for _, agent in sorted(self._agents.items())]

    def __contains__(self, agent_type: object) -> bool:
        return agent_type in self._agents

    def __len__(self) -> int:
        return len(self._agents)
