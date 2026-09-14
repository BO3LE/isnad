from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from contracts.graph import CycleError, topological_order
from contracts.run import WorkflowGraph
from db.models import AgentNode, Workflow


def ordered_nodes(graph: WorkflowGraph):
    try:
        return topological_order(graph)
    except CycleError:
        return sorted(graph.nodes, key=lambda n: (n.position.x, n.position.y))


def save_graph(session: Session, workflow: Workflow, graph: WorkflowGraph) -> None:
    """`graph_definition` is the source of truth; `agent_nodes` is derived from it on every save."""
    workflow.graph_definition = graph.model_dump(mode="json")
    session.flush()
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
