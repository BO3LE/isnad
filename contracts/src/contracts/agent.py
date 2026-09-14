"""BaseAgent — the one interface the worker knows."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

from contracts.manifest import AgentManifest
from contracts.ports import Ports

InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


class BaseAgent(ABC, Generic[InT, OutT]):
    manifest: ClassVar[AgentManifest]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    config_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def execute(self, input_data: InT, ports: Ports) -> OutT:
        """Do exactly one job and return a validated result. No DB, no queue, no other agents."""

    @classmethod
    def catalog_entry(cls) -> AgentManifest:
        return cls.manifest.model_copy(update={"config_schema": cls.config_model.model_json_schema()})

    @staticmethod
    def load_manifest(agent_file: str) -> AgentManifest:
        """Read the `manifest.json` that sits next to the agent module. Call as `load_manifest(__file__)`."""
        raw = Path(agent_file).with_name("manifest.json").read_text(encoding="utf-8")
        return AgentManifest.model_validate(json.loads(raw))
