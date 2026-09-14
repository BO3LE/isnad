"""Two fake agents, registered directly — the orchestrator suite needs no real agent installed.

The decoupling test from GP-plan C3: delete the whole `agents/` folder and this suite still passes.
"""

from __future__ import annotations

import itertools
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from adapters.factory import AdapterSettings, build_ports
from contracts.agent import BaseAgent
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.manifest import AgentManifest
from contracts.run import GraphEdge, GraphNode, Position, WorkflowGraph
from worker.registry import Registry
from worker.testing import InMemoryRunStore


class TextIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str


class TextOut(BaseModel):
    text: str


class ShoutConfig(BaseModel):
    text: str = "hello"


def _manifest(name: str, approval: bool = False) -> AgentManifest:
    return AgentManifest(
        name=name,
        version="0.1.0",
        title=name.title(),
        description="test agent",
        input_type="TextIn",
        output_type="TextOut",
        requires_approval=approval,
    )


class ShoutAgent(BaseAgent[TextIn, TextOut]):
    manifest = _manifest("shout")
    input_model, output_model, config_model = TextIn, TextOut, ShoutConfig

    async def execute(self, input_data, ports):
        return TextOut(text=input_data.text.upper())


class ReverseAgent(BaseAgent[TextIn, TextOut]):
    manifest = _manifest("reverse")
    input_model, output_model, config_model = TextIn, TextOut, ShoutConfig
    failures_before_success: ClassVar[int] = 0
    calls: ClassVar[int] = 0
    non_retryable: ClassVar[bool] = False

    async def execute(self, input_data, ports):
        type(self).calls += 1
        if type(self).calls <= type(self).failures_before_success:
            if type(self).non_retryable:
                raise NonRetryableAgentError("Your Google connection has expired.")
            raise AgentError("Couldn't reach the service.")
        return TextOut(text=input_data.text[::-1])


class GateAgent(BaseAgent[TextIn, TextOut]):
    manifest = _manifest("gate", approval=True)
    input_model, output_model, config_model = TextIn, TextOut, ShoutConfig

    async def execute(self, input_data, ports):
        return TextOut(text=f"published:{input_data.text}")


@pytest.fixture(autouse=True)
def _reset_reverse():
    ReverseAgent.calls = 0
    ReverseAgent.failures_before_success = 0
    ReverseAgent.non_retryable = False


@pytest.fixture()
def registry() -> Registry:
    return Registry([ShoutAgent, ReverseAgent, GateAgent])


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


@pytest.fixture()
def store() -> InMemoryRunStore:
    return InMemoryRunStore()


class Sleeps(list):
    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


@pytest.fixture()
def sleeps() -> Sleeps:
    return Sleeps()


def chain(*agent_types: str, config: dict | None = None) -> WorkflowGraph:
    nodes = [
        GraphNode(
            id=uuid4(), agent_type=t, position=Position(x=i * 300), configuration=(config or {}) if i == 0 else {}
        )
        for i, t in enumerate(agent_types)
    ]
    edges = [GraphEdge(id=f"e{i}", source=a.id, target=b.id) for i, (a, b) in enumerate(itertools.pairwise(nodes))]
    return WorkflowGraph(nodes=nodes, edges=edges)
