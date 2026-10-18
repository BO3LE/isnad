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
from contracts.manifest import AgentFamily, AgentManifest
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


def _manifest(name: str, approval: bool = False, family: AgentFamily = AgentFamily.CREATE) -> AgentManifest:
    return AgentManifest(
        name=name,
        version="0.1.0",
        title=name.title(),
        description="test agent",
        family=family,
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


class SendAgent(BaseAgent[TextIn, TextOut]):
    """A distribute agent whose manifest forgot to ask for approval — the Email change in PR #40."""

    manifest = _manifest("send", approval=False, family=AgentFamily.DISTRIBUTE)
    input_model, output_model, config_model = TextIn, TextOut, ShoutConfig
    calls: ClassVar[int] = 0

    async def execute(self, input_data, ports):
        type(self).calls += 1
        return TextOut(text=f"sent:{input_data.text}")


class DraftAgent(BaseAgent[TextIn, TextOut]):
    """Writes a draft, redoes it with the reviewer's note, and marks an edited draft as kept."""

    manifest = _manifest("draft")
    input_model, output_model, config_model = TextIn, TextOut, ShoutConfig
    revisions: ClassVar[list] = []
    edits: ClassVar[list] = []
    edit_fails: ClassVar[bool] = False

    async def execute(self, input_data, ports):
        return TextOut(text=f"draft of {input_data.text}")

    async def revise(self, input_data, ports, revision):
        type(self).revisions.append(revision)
        return TextOut(text=f"{revision.previous['text']}, {revision.note}")

    async def accept_edit(self, output, ports):
        type(self).edits.append(output.text)
        if type(self).edit_fails:
            raise NonRetryableAgentError("The edited draft couldn't be saved as a PDF.")
        return TextOut(text=f"{output.text} (kept)")


@pytest.fixture(autouse=True)
def _reset_reverse():
    ReverseAgent.calls = 0
    ReverseAgent.failures_before_success = 0
    ReverseAgent.non_retryable = False
    SendAgent.calls = 0
    DraftAgent.revisions, DraftAgent.edits, DraftAgent.edit_fails = [], [], False


@pytest.fixture()
def registry() -> Registry:
    return Registry([ShoutAgent, ReverseAgent, GateAgent, SendAgent, DraftAgent])


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


def chain(*agent_types: str, config: dict | None = None, review: tuple[int, ...] = ()) -> WorkflowGraph:
    """Steps one after another; those at the `review` positions wait for a person with their result."""
    nodes = [
        GraphNode(
            id=uuid4(),
            agent_type=t,
            position=Position(x=i * 300),
            configuration=(config or {}) if i == 0 else {},
            requires_approval=i in review,
        )
        for i, t in enumerate(agent_types)
    ]
    edges = [GraphEdge(id=f"e{i}", source=a.id, target=b.id) for i, (a, b) in enumerate(itertools.pairwise(nodes))]
    return WorkflowGraph(nodes=nodes, edges=edges)
