"""Pure graph helpers shared by the API (validation) and the worker (execution order).

Standard library only, operating on contract types.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from contracts.run import GraphNode, WorkflowGraph


class CycleError(ValueError):
    def __init__(self, cycle: list[UUID]):
        self.cycle = cycle
        super().__init__("workflow graph contains a cycle")


def parents(graph: WorkflowGraph) -> dict[UUID, list[UUID]]:
    result: dict[UUID, list[UUID]] = defaultdict(list)
    for edge in graph.edges:
        result[edge.target].append(edge.source)
    return result


def children(graph: WorkflowGraph) -> dict[UUID, list[UUID]]:
    result: dict[UUID, list[UUID]] = defaultdict(list)
    for edge in graph.edges:
        result[edge.source].append(edge.target)
    return result


def find_cycle(graph: WorkflowGraph) -> list[UUID] | None:
    """Return one cycle as a list of node ids (first id repeated at the end), or None."""
    adjacency = children(graph)
    white, grey, black = 0, 1, 2
    colour: dict[UUID, int] = {n.id: white for n in graph.nodes}
    stack: list[UUID] = []

    def visit(node_id: UUID) -> list[UUID] | None:
        colour[node_id] = grey
        stack.append(node_id)
        for nxt in adjacency.get(node_id, []):
            if colour.get(nxt) == grey:
                return [*stack[stack.index(nxt) :], nxt]
            if colour.get(nxt) == white:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        colour[node_id] = black
        return None

    for node in graph.nodes:
        if colour[node.id] == white:
            found = visit(node.id)
            if found:
                return found
    return None


def topological_order(graph: WorkflowGraph) -> list[GraphNode]:
    """Kahn's algorithm. Ties are broken left-to-right by canvas position, so order is stable."""
    by_id = {n.id: n for n in graph.nodes}
    indegree = {n.id: 0 for n in graph.nodes}
    adjacency = children(graph)
    for edge in graph.edges:
        if edge.target in indegree and edge.source in indegree:
            indegree[edge.target] += 1

    def sort_key(node_id: UUID) -> tuple[float, float, str]:
        node = by_id[node_id]
        return (node.position.x, node.position.y, str(node_id))

    ready = sorted((nid for nid, deg in indegree.items() if deg == 0), key=sort_key)
    order: list[GraphNode] = []
    while ready:
        current = ready.pop(0)
        order.append(by_id[current])
        for nxt in adjacency.get(current, []):
            if nxt not in indegree:
                continue
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort(key=sort_key)

    if len(order) != len(graph.nodes):
        raise CycleError(find_cycle(graph) or [])
    return order


def descendants(graph: WorkflowGraph, node_id: UUID) -> set[UUID]:
    adjacency = children(graph)
    seen: set[UUID] = set()
    frontier = list(adjacency.get(node_id, []))
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(adjacency.get(current, []))
    return seen


def ancestors(graph: WorkflowGraph, node_id: UUID) -> set[UUID]:
    """Every node with a path to `node_id`."""
    upstream = parents(graph)
    seen: set[UUID] = set()
    frontier = list(upstream.get(node_id, []))
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(upstream.get(current, []))
    return seen
