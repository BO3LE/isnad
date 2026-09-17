"""The shape every agent publishes in its `manifest.json`."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentFamily(StrEnum):
    CREATE = "create"
    DISTRIBUTE = "distribute"


class AgentInput(BaseModel):
    """One thing an agent needs to run, and where it may come from."""

    model_config = ConfigDict(extra="forbid")

    name: str
    accepts: list[str] = Field(
        description="Output names an earlier step may supply this under, in the order the agent prefers them"
    )
    required: bool = Field(description="The step cannot run without it")
    settable: bool = Field(
        description="The user can type it in the step's settings; otherwise only an earlier step can supply it"
    )


class AgentOutput(BaseModel):
    """One thing an agent hands on to the steps after it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    title: str = Field(description="What a person calls it, e.g. 'article'")


class AgentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64, description="Unique agent_type")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=200)
    family: AgentFamily = AgentFamily.CREATE
    icon: str | None = Field(None, description="Lucide icon name, e.g. 'telescope'")
    input_type: str = Field(description="Model name in contracts.agent_io")
    output_type: str = Field(description="Model name in contracts.agent_io")
    requires_approval: bool = Field(False, description="True for agents that send content out of the platform")
    config_schema: dict[str, Any] | None = Field(
        None, description="JSON Schema of the configuration form. Filled from the agent's config model at runtime."
    )
    inputs: list[AgentInput] = Field(
        default_factory=list, description="What the agent needs. Filled from its input model at runtime."
    )
    outputs: list[AgentOutput] = Field(
        default_factory=list, description="What the agent hands on. Filled from its output model at runtime."
    )
