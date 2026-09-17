"""BaseAgent — the one interface the worker knows."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from pydantic import AliasChoices, BaseModel

from contracts.manifest import AgentInput, AgentManifest, AgentOutput
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
        return cls.manifest.model_copy(
            update={
                "config_schema": cls.config_model.model_json_schema(),
                "inputs": describe_inputs(cls.input_model, cls.config_model),
                "outputs": describe_outputs(cls.output_model),
            }
        )

    @staticmethod
    def load_manifest(agent_file: str) -> AgentManifest:
        """Read the `manifest.json` that sits next to the agent module. Call as `load_manifest(__file__)`."""
        raw = Path(agent_file).with_name("manifest.json").read_text(encoding="utf-8")
        return AgentManifest.model_validate(json.loads(raw))


def describe_inputs(input_model: type[BaseModel], config_model: type[BaseModel]) -> list[AgentInput]:
    """What an agent needs, read from its input model — so the canvas can say where each value comes from.

    The worker merges earlier steps' outputs and validates them against the input model, so a
    field's validation aliases are exactly the output names it will pick up (Video's `script`
    accepts Writer's `article_md`).
    """
    inputs = []
    for name, field in input_model.model_fields.items():
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            accepts = [choice for choice in alias.choices if isinstance(choice, str)]
        elif isinstance(alias, str):
            accepts = [alias]
        else:
            accepts = [name]
        inputs.append(
            AgentInput(
                name=name,
                accepts=accepts,
                required=field.is_required(),
                settable=name in config_model.model_fields,
            )
        )
    return inputs


def describe_outputs(output_model: type[BaseModel]) -> list[AgentOutput]:
    """What an agent hands on. A field's `title` is its human name; otherwise the name is tidied up."""
    return [
        AgentOutput(name=name, title=field.title or name.replace("_", " "))
        for name, field in output_model.model_fields.items()
    ]
