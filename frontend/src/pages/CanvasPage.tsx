import { useMutation, useQuery } from "@tanstack/react-query";
import { Play, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "reactflow";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/design-system/components/Button";
import { ApiError, endpoints, type AgentManifest, type ValidationResult, type WorkflowGraph } from "@/lib/api";

// S-03 skeleton (DESIGN-SYSTEM.md §15, §21). Proves the loop: catalog → canvas → save → validate → run.
// TODO(W2–W3, Ahmed): custom AgentNode (§15.2), drag from palette, schema-driven drawer (§17), run mode (§15.10).

type NodeData = { label: string; agentType: string; configuration: Record<string, unknown>; requiresApproval: boolean };

function toFlow(graph: WorkflowGraph, catalog: AgentManifest[]): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const title = (type: string) => catalog.find((a) => a.name === type)?.title ?? type;
  return {
    nodes: (graph.nodes ?? []).map((n) => ({
      id: n.id,
      position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
      data: { label: title(n.agent_type), agentType: n.agent_type, configuration: n.configuration ?? {}, requiresApproval: n.requires_approval ?? false },
    })),
    edges: (graph.edges ?? []).map((e) => ({ id: e.id, source: e.source, target: e.target })),
  };
}

function toGraph(nodes: Node<NodeData>[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      agent_type: n.data.agentType,
      configuration: n.data.configuration,
      requires_approval: n.data.requiresApproval,
      position: n.position,
    })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
  };
}

export function CanvasPage() {
  const { workflowId = "" } = useParams();
  const navigate = useNavigate();
  const workflow = useQuery({ queryKey: ["workflow", workflowId], queryFn: () => endpoints.workflow(workflowId) });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog });
  const [nodes, setNodes, onNodesChange] = useNodesState<NodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workflow.data && catalog.data) {
      const flow = toFlow(workflow.data.graph, catalog.data);
      setNodes(flow.nodes);
      setEdges(flow.edges);
    }
  }, [workflow.data, catalog.data, setNodes, setEdges]);

  const onConnect = useCallback((c: Connection) => setEdges((eds) => addEdge({ ...c, id: crypto.randomUUID() }, eds)), [setEdges]);

  const addAgent = (agent: AgentManifest) =>
    setNodes((ns) => [
      ...ns,
      {
        id: crypto.randomUUID(),
        position: { x: 80 + ns.length * 280, y: 160 },
        data: { label: agent.title, agentType: agent.name, configuration: {}, requiresApproval: agent.requires_approval ?? false },
      },
    ]);

  const save = () => endpoints.saveWorkflow(workflowId, { graph: toGraph(nodes, edges) });

  const validate = useMutation({
    mutationFn: async () => {
      await save();
      return endpoints.validate(workflowId);
    },
    onSuccess: setValidation,
  });

  const run = useMutation({
    mutationFn: async () => {
      await save();
      return endpoints.run(workflowId);
    },
    onSuccess: (created) => navigate(`/runs/${created.run_id}`),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 422) {
        setValidation((err.body as { detail: ValidationResult }).detail);
      } else setError(err.message);
    },
  });

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <span className="truncate text-body-md text-text-muted">
          Workflows / <span className="text-text">{workflow.data?.name ?? "…"}</span>
        </span>
        <div className="ml-auto flex gap-2">
          <Button onClick={() => validate.mutate()} loading={validate.isPending}>
            <ShieldCheck size={16} aria-hidden /> Validate
          </Button>
          <Button variant="accent" onClick={() => run.mutate()} loading={run.isPending}>
            <Play size={16} aria-hidden /> Run
          </Button>
        </div>
      </TopBar>
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-[264px] shrink-0 overflow-y-auto border-r border-border bg-surface p-3 lg:block" aria-label="Agents">
          <p className="mb-2 px-1 text-overline uppercase text-text-muted">Agents</p>
          {catalog.data?.length === 0 && <p className="px-1 text-body-sm text-text-muted">No agents yet — start the worker.</p>}
          <ul className="grid gap-1">
            {catalog.data?.map((agent) => (
              <li key={agent.name}>
                <button onClick={() => addAgent(agent)} className="grid w-full gap-0.5 rounded-sm p-2 text-left hover:bg-surface-hover">
                  <span className="text-body-md font-medium">{agent.title}</span>
                  <span className="truncate text-body-sm text-text-muted">{agent.description}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <div className="relative min-w-0 flex-1 bg-bg-sunken">
          <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView>
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--color-canvas-dot)" />
            <Controls />
          </ReactFlow>
          {(validation || error) && (
            <section className="absolute inset-x-4 bottom-4 max-h-[40%] overflow-y-auto rounded-md border border-border bg-surface p-4 shadow-3" aria-live="polite">
              {error && <p className="text-status-failed-fg">{error}</p>}
              {validation?.valid && <p className="text-status-success-fg">Ready to run.</p>}
              <ul className="grid gap-1">
                {validation?.issues.map((issue, i) => (
                  <li key={i} className={issue.severity === "error" ? "text-status-failed-fg" : "text-status-retrying-fg"}>
                    {issue.message}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
