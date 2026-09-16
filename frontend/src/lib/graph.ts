import type { AgentManifest, GraphNode, WorkflowGraph } from "./api";

// Pure graph logic for the canvas (DESIGN-SYSTEM.md §15). No React, no React Flow — so the rules
// that decide whether a chain is even shaped correctly can be tested without a DOM.

export const GRID = 16;

export interface FlowEdgeLike {
  id: string;
  source: string;
  target: string;
}

/** §15.3 — new nodes snap to the 16 px grid, dropped at the cursor or added at the viewport centre. */
export function snapToGrid(value: number, grid: number = GRID): number {
  return Math.round(value / grid) * grid;
}

/**
 * §15.3 — "A node can't connect to itself; a connection that would create a cycle is refused."
 *
 * Structural rules only. Type compatibility is deliberately not decided here: the catalog's
 * input/output types are nominal per agent (ResearchOutput, WriteInput), so there is no map that
 * says which may follow which. The spec's own fallback applies — allow the drop and let
 * POST /validate report it, because the server owns validation (§15.5).
 */
export type ConnectionRefusal = "self" | "cycle" | "duplicate" | null;

export function refuseConnection(edges: FlowEdgeLike[], source: string, target: string): ConnectionRefusal {
  if (source === target) return "self";
  if (edges.some((e) => e.source === source && e.target === target)) return "duplicate";
  if (reaches(edges, target, source)) return "cycle";
  return null;
}

/** Can we already get from `from` to `to` by following edges? Then source→target closes a loop. */
function reaches(edges: FlowEdgeLike[], from: string, to: string): boolean {
  const seen = new Set<string>();
  const queue = [from];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === to) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of edges) if (edge.source === current) queue.push(edge.target);
  }
  return false;
}

/**
 * §15.2 — the node's sub-label reads "WRITER · STEP 2". The step is the node's topological
 * position, so it only means anything once the chain is connected.
 *
 * Kahn's algorithm. A node inside a cycle never becomes ready and is simply left without a step
 * rather than crashing or looping — /validate is what tells the user about the cycle.
 */
export function stepNumbers(nodeIds: string[], edges: FlowEdgeLike[]): Map<string, number> {
  const incoming = new Map<string, number>(nodeIds.map((id) => [id, 0]));
  for (const edge of edges) {
    if (incoming.has(edge.target)) incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
  }

  const steps = new Map<string, number>();
  let ready = nodeIds.filter((id) => incoming.get(id) === 0);
  let step = 1;

  while (ready.length > 0) {
    // Stable ordering so the numbers do not shuffle between renders.
    ready.sort((a, b) => nodeIds.indexOf(a) - nodeIds.indexOf(b));
    const next: string[] = [];
    for (const id of ready) {
      steps.set(id, step);
      for (const edge of edges) {
        if (edge.source !== id || !incoming.has(edge.target)) continue;
        const remaining = (incoming.get(edge.target) ?? 1) - 1;
        incoming.set(edge.target, remaining);
        if (remaining === 0) next.push(edge.target);
      }
    }
    ready = next;
    step += 1;
  }

  return steps;
}

/** A short "Medium · Informative · Blog post" line from the node's configuration (§15.2). */
export function configSummary(configuration: Record<string, unknown> | null | undefined, limit = 3): string {
  if (!configuration) return "";
  return Object.values(configuration)
    .filter((value) => value !== null && value !== undefined && value !== "" && !Array.isArray(value))
    .slice(0, limit)
    .map((value) => (typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)))
    .join(" · ");
}

/** Distribute agents always require approval (D-08), whatever the graph says. */
export function approvalIsLocked(agentType: string, catalog: AgentManifest[]): boolean {
  return catalog.find((a) => a.name === agentType)?.requires_approval === true;
}

/** The API's graph shape, rebuilt from what is on the canvas. */
export function toWorkflowGraph(
  nodes: { id: string; position: { x: number; y: number }; data: { agentType: string; configuration: Record<string, unknown>; requiresApproval: boolean } }[],
  edges: FlowEdgeLike[],
): WorkflowGraph {
  return {
    nodes: nodes.map(
      (n): GraphNode => ({
        id: n.id,
        agent_type: n.data.agentType,
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
        configuration: n.data.configuration,
        requires_approval: n.data.requiresApproval,
      }),
    ),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  };
}

/** True when two graphs are the same, so autosave does not PUT a graph nobody changed. */
export function graphsEqual(a: WorkflowGraph | null, b: WorkflowGraph | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
