from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from contracts.graph import CycleError, topological_order
from contracts.run import WorkflowGraph
from db.models import AgentNode, Workflow


def ordered_nodes(graph: WorkflowGraph):
    try:
        return topological_order(graph)
    except CycleError:
        return sorted(graph.nodes, key=lambda n: (n.position.x, n.position.y))


DUPLICATE_STEPS = "Two steps share the same id. Delete one and add it again."
STEPS_TAKEN = "A step's id is already used by another workflow. Give copied steps new ids."


class GraphNotSaved(ValueError):
    """A graph `agent_nodes` can't hold. `status_code` is what the API answers."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code, self.message = status_code, message


def save_graph(session: Session, workflow: Workflow, graph: WorkflowGraph) -> None:
    """`graph_definition` is the source of truth; `agent_nodes` is derived from it on every save.

    A step's id is the primary key of its `agent_nodes` row, so it is unique across every workflow.
    A graph copied from another workflow with its ids kept, or with two steps sharing one, used to
    fail the insert with a 500; it is refused with a readable answer instead — without saying whose
    workflow already holds the id.
    """
    ids = [node.id for node in graph.nodes]
    if len(set(ids)) != len(ids):
        raise GraphNotSaved(422, DUPLICATE_STEPS)
    workflow.graph_definition = graph.model_dump(mode="json")
    session.flush()
    if ids and session.scalar(
        select(func.count()).select_from(AgentNode).where(AgentNode.id.in_(ids), AgentNode.workflow_id != workflow.id)
    ):
        raise GraphNotSaved(409, STEPS_TAKEN)
    session.execute(delete(AgentNode).where(AgentNode.workflow_id == workflow.id))
    for order, node in enumerate(ordered_nodes(graph)):
        session.add(
            AgentNode(
                id=node.id,
                workflow_id=workflow.id,
                agent_type=node.agent_type,
                configuration=node.configuration,
                position_order=order,
            )
        )
