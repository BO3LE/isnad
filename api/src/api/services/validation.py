"""Graph validation (`POST /workflows/{id}/validate`).

Every message is written for a person, not a log file: "Writer isn't connected to anything",
not "validation failed". Wording follows DESIGN-SYSTEM.md §23.3. The frontend renders these
messages as-is and never invents its own rules.
"""

from __future__ import annotations

from collections.abc import Mapping

from api.schemas import ValidationIssue
from api.services.credentials import status_of
from contracts.graph import find_cycle
from contracts.manifest import AgentManifest
from contracts.run import WorkflowGraph
from db.models import Credential


def validate_graph(
    graph: WorkflowGraph,
    catalog: list[AgentManifest] | None,
    credentials: Mapping[str, Credential] | None = None,
    *,
    require_credentials: bool = False,
) -> list[ValidationIssue]:
    """`credentials` (id → the owner's rows) turns on the connection checks; None skips them."""
    issues: list[ValidationIssue] = []
    by_type = {m.name: m for m in catalog or []}
    nodes = {n.id: n for n in graph.nodes}

    def name(node_id) -> str:
        node = nodes[node_id]
        return (
            by_type[node.agent_type].title if node.agent_type in by_type else node.agent_type.replace("_", " ").title()
        )

    if not graph.nodes:
        return [ValidationIssue(code="empty_workflow", message="Add at least one agent before running.")]

    if len(nodes) != len(graph.nodes):
        issues.append(
            ValidationIssue(code="duplicate_node", message="Two steps share the same id. Delete one and add it again.")
        )

    valid_edges = []
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            issues.append(
                ValidationIssue(
                    code="invalid_edge", edge_id=edge.id, message="A connection points to a step that no longer exists."
                )
            )
        elif edge.source == edge.target:
            issues.append(
                ValidationIssue(
                    code="cycle_detected",
                    edge_id=edge.id,
                    node_id=edge.source,
                    message=f"{name(edge.source)} can't connect to itself.",
                )
            )
        else:
            valid_edges.append(edge)

    clean = WorkflowGraph(nodes=list(nodes.values()), edges=valid_edges)
    cycle = find_cycle(clean)
    if cycle:
        path = " → ".join(name(n) for n in cycle)
        issues.append(
            ValidationIssue(
                code="cycle_detected",
                node_id=cycle[0],
                message=f"These steps form a loop: {path}. Remove one connection.",
            )
        )

    if len(nodes) > 1:
        connected = {e.source for e in valid_edges} | {e.target for e in valid_edges}
        for node_id in nodes:
            if node_id not in connected:
                issues.append(
                    ValidationIssue(
                        code="orphan_node", node_id=node_id, message=f"{name(node_id)} isn't connected to anything."
                    )
                )

    if catalog is None:
        issues.append(
            ValidationIssue(
                code="catalog_unavailable",
                severity="warning",
                message="Agent settings couldn't be checked because the worker hasn't started yet.",
            )
        )
        return issues

    for node in nodes.values():
        manifest = by_type.get(node.agent_type)
        if manifest is None:
            issues.append(
                ValidationIssue(
                    code="unknown_agent", node_id=node.id, message=f"No agent is installed for “{node.agent_type}”."
                )
            )
            continue
        schema = manifest.config_schema or {}
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if node.configuration.get(field) in (None, "", []):
                label = properties.get(field, {}).get("title", field.replace("_", " "))
                issues.append(
                    ValidationIssue(
                        code="missing_config", node_id=node.id, message=f"{manifest.title} is missing {label.lower()}."
                    )
                )
        if credentials is not None:
            issues.extend(_credential_issues(node, manifest, properties, credentials, require_credentials))
    return issues


def _credential_issues(node, manifest: AgentManifest, properties: dict, credentials, required: bool):
    """Fields marked `x-widget: credential` hold a reference to one of this user's connections.

    With real adapters a missing or expired connection blocks the run; with fakes (nothing is really
    sent) it is only a warning, so the templates still run on a fresh checkout.
    """
    severity = "error" if required else "warning"
    for field, prop in properties.items():
        if prop.get("x-widget") != "credential":
            continue
        ref = node.configuration.get(field)
        row = credentials.get(str(ref)) if ref else None
        if row is None:
            yield ValidationIssue(
                code="missing_credential",
                node_id=node.id,
                severity=severity,
                message=f"{manifest.title} needs a Google connection.",
            )
        elif status_of(row) == "expired":
            yield ValidationIssue(
                code="expired_credential",
                node_id=node.id,
                severity=severity,
                message=f"{manifest.title}'s Google connection has expired.",
            )
