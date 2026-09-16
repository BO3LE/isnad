import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Redo2, ShieldCheck, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
} from "reactflow";
import { AppShell } from "@/components/app/AppShell";
import { AgentNode, type AgentNodeData } from "@/components/canvas/AgentNode";
import { AGENT_DRAG_TYPE, AgentPalette } from "@/components/canvas/AgentPalette";
import { CanvasStatusBar } from "@/components/canvas/CanvasStatusBar";
import { useGraphHistory } from "@/components/canvas/useGraphHistory";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { Button } from "@/design-system/components/Button";
import { IconButton } from "@/design-system/components/IconButton";
import { Spinner } from "@/design-system/components/Progress";
import { Tooltip } from "@/design-system/components/Tooltip";
import { useToast } from "@/design-system/components/toast-context";
import { NotFoundState } from "@/pages/NotFoundPage";
import { ApiError, endpoints, type AgentManifest, type ValidationResult, type WorkflowOut } from "@/lib/api";
import { GRID, configSummary, graphsEqual, refuseConnection, snapToGrid, stepNumbers, toWorkflowGraph } from "@/lib/graph";

// P-04 · Workflow Canvas (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §15, §21 S-03.
// The configuration drawer (S-04) and the validation panel (§15.5) are Part 3c; this is the canvas
// itself — palette, nodes, edges, autosave, undo/redo and the status bar.

const AUTOSAVE_DELAY = 800; // §15.4
const nodeTypes: NodeTypes = { agent: AgentNode };

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: number } | { kind: "error" };

function CanvasPageInner() {
  const { workflowId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { screenToFlowPosition, getViewport, fitView } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [zoom, setZoom] = useState(1);
  const [name, setName] = useState("");
  const [editingName, setEditingName] = useState(false);

  const history = useGraphHistory<AgentNodeData>({ nodes: [], edges: [] });
  const loadedGraph = useRef<string>("");
  // The graph as the server has it, normalised through toWorkflowGraph. Comparing against the raw
  // payload instead made every page open look like an edit — the canvas PUT on load, every time.
  const savedGraph = useRef<ReturnType<typeof toWorkflowGraph> | null>(null);
  const saveTimer = useRef<number>();
  const wrapper = useRef<HTMLDivElement>(null);

  const workflow = useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => endpoints.workflow(workflowId),
    enabled: Boolean(workflowId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog });

  const agents: AgentManifest[] = useMemo(() => catalog.data ?? [], [catalog.data]);

  // ---------------------------------------------------------------- load
  useEffect(() => {
    const data = workflow.data;
    if (!data || loadedGraph.current === data.id) return;
    loadedGraph.current = data.id;
    setName(data.name);

    const loadedNodes = (data.graph?.nodes ?? []).map((node) => ({
      id: node.id,
      type: "agent",
      position: { x: node.position?.x ?? 0, y: node.position?.y ?? 0 },
      data: {
        agentType: node.agent_type,
        title: node.agent_type,
        summary: configSummary(node.configuration as Record<string, unknown>),
        requiresApproval: node.requires_approval ?? false,
        configuration: (node.configuration ?? {}) as Record<string, unknown>,
      } as AgentNodeData & { configuration: Record<string, unknown> },
    }));
    const loadedEdges = (data.graph?.edges ?? []).map((edge) => ({ id: edge.id, source: edge.source, target: edge.target }));

    setNodes(loadedNodes);
    setEdges(loadedEdges);
    // Normalise through the same function the autosave comparison uses, or the first comparison
    // always differs and the canvas saves a graph nobody touched.
    savedGraph.current = toWorkflowGraph(loadedNodes as unknown as Parameters<typeof toWorkflowGraph>[0], loadedEdges);
    history.reset();
  }, [workflow.data, setNodes, setEdges, history]);

  // Titles and icons come from the catalog, which may arrive after the graph.
  const steps = useMemo(() => stepNumbers(nodes.map((n) => n.id), edges), [nodes, edges]);
  const issuesByNode = useMemo(() => {
    const map = new Map<string, number>();
    for (const issue of validation?.issues ?? []) {
      if (issue.node_id) map.set(issue.node_id, (map.get(issue.node_id) ?? 0) + 1);
    }
    return map;
  }, [validation]);

  const decorated = useMemo(
    () =>
      nodes.map((node) => {
        const manifest = agents.find((a) => a.name === node.data.agentType);
        return {
          ...node,
          data: {
            ...node.data,
            title: agentTitle(node.data.agentType, agents),
            icon: manifest?.icon,
            family: manifest?.family,
            step: steps.get(node.id),
            issueCount: issuesByNode.get(node.id) ?? 0,
          },
        };
      }),
    [nodes, agents, steps, issuesByNode],
  );

  // ---------------------------------------------------------------- autosave (§15.4)
  const graph = useMemo(
    () => toWorkflowGraph(nodes as unknown as Parameters<typeof toWorkflowGraph>[0], edges),
    [nodes, edges],
  );

  const persist = useCallback(async () => {
    setSave({ kind: "saving" });
    try {
      await endpoints.saveWorkflow(workflowId, { graph });
      savedGraph.current = graph;
      setSave({ kind: "saved", at: Date.now() });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    } catch {
      setSave({ kind: "error" });
    }
  }, [graph, workflowId, queryClient]);

  useEffect(() => {
    if (!workflow.data || loadedGraph.current !== workflow.data.id) return;
    if (graphsEqual(graph, savedGraph.current)) return;

    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(persist, AUTOSAVE_DELAY);
    return () => window.clearTimeout(saveTimer.current);
  }, [graph, persist, workflow.data]);

  // ---------------------------------------------------------------- editing
  const snapshot = useCallback(() => ({ nodes, edges }), [nodes, edges]);

  const addNode = useCallback(
    (agentType: string, at?: { x: number; y: number }) => {
      const manifest = agents.find((a) => a.name === agentType);
      const viewport = getViewport();
      const box = wrapper.current?.getBoundingClientRect();
      const centre =
        at ??
        screenToFlowPosition({
          x: (box?.left ?? 0) + (box?.width ?? 800) / 2,
          y: (box?.top ?? 0) + (box?.height ?? 600) / 2,
        });
      void viewport;

      history.commit(snapshot());
      setNodes((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          type: "agent",
          position: { x: snapToGrid(centre.x), y: snapToGrid(centre.y) },
          data: {
            agentType,
            title: manifest?.title ?? agentType,
            summary: "",
            // D-08: Distribute agents always require approval, and the catalog is what says so.
            requiresApproval: manifest?.requires_approval ?? false,
            configuration: {},
          } as AgentNodeData & { configuration: Record<string, unknown> },
        },
      ]);
    },
    [agents, getViewport, screenToFlowPosition, history, snapshot, setNodes],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const { source, target } = connection;
      if (!source || !target) return;

      const refusal = refuseConnection(edges, source, target);
      if (refusal === "cycle") return toast({ variant: "error", message: "That connection would create a loop." });
      if (refusal === "self") return toast({ variant: "error", message: "A step can't feed itself." });
      if (refusal === "duplicate") return;

      history.commit(snapshot());
      setEdges((current) => addEdge({ ...connection, id: `${source}-${target}` }, current));
    },
    [edges, history, snapshot, setEdges, toast],
  );

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const agentType = event.dataTransfer.getData(AGENT_DRAG_TYPE);
      if (!agentType) return;
      addNode(agentType, screenToFlowPosition({ x: event.clientX, y: event.clientY }));
    },
    [addNode, screenToFlowPosition],
  );

  const applySnapshot = useCallback(
    (next: { nodes: Node<AgentNodeData>[]; edges: Edge[] } | null) => {
      if (!next) return;
      setNodes(next.nodes);
      setEdges(next.edges);
    },
    [setNodes, setEdges],
  );

  // §13 keyboard: ⌘Z / ⌘⇧Z anywhere on the canvas.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
      event.preventDefault();
      applySnapshot(event.shiftKey ? history.redo(snapshot()) : history.undo(snapshot()));
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [history, snapshot, applySnapshot]);

  // ---------------------------------------------------------------- actions
  const validate = useMutation({
    mutationFn: () => endpoints.validate(workflowId),
    onSuccess: (result) => {
      setValidation(result);
      if (result.valid) toast({ variant: "success", message: "Ready to run." });
    },
    onError: () => toast({ variant: "error", message: "Couldn't validate the workflow." }),
  });

  const run = useMutation({
    mutationFn: () => endpoints.run(workflowId),
    onSuccess: (created) => navigate(`/runs/${created.run_id}`),
    onError: (error) =>
      toast({
        variant: "error",
        message: error instanceof ApiError ? error.message : "Couldn't start the run.",
      }),
  });

  function commitName() {
    setEditingName(false);
    const trimmed = name.trim();
    if (!trimmed || trimmed === workflow.data?.name) return setName(workflow.data?.name ?? "");
    endpoints
      .renameWorkflow(workflowId, trimmed)
      .then(() => queryClient.invalidateQueries({ queryKey: ["workflows"] }))
      .catch(() => {
        setName(workflow.data?.name ?? "");
        toast({ variant: "error", message: "Couldn't rename the workflow." });
      });
  }

  if (workflow.isError && workflow.error instanceof ApiError && workflow.error.status === 404) {
    return (
      <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Not found" }]}>
        <NotFoundState message="This workflow doesn't exist, or it isn't yours." />
      </AppShell>
    );
  }

  const saveLabel =
    save.kind === "saving"
      ? "Saving…"
      : save.kind === "saved"
        ? "Saved · just now"
        : save.kind === "error"
          ? "Not saved — retrying"
          : "";

  return (
    <AppShell
      fullBleed
      crumbs={[{ label: "Workflows", to: "/workflows" }, { label: name || "Untitled workflow" }]}
      status={
        <span className={`text-body-sm ${save.kind === "error" ? "text-status-failed-fg" : "text-text-muted"}`}>
          {saveLabel}
          {save.kind === "error" && (
            <button type="button" onClick={persist} className="ml-2 text-interactive hover:underline">
              Retry
            </button>
          )}
        </span>
      }
      actions={
        <div className="flex items-center gap-2">
          <Tooltip content="Undo (⌘Z)">
            <IconButton
              label="Undo"
              icon={<Undo2 size={16} aria-hidden />}
              disabled={!history.canUndo}
              onClick={() => applySnapshot(history.undo(snapshot()))}
            />
          </Tooltip>
          <Tooltip content="Redo (⌘⇧Z)">
            <IconButton
              label="Redo"
              icon={<Redo2 size={16} aria-hidden />}
              disabled={!history.canRedo}
              onClick={() => applySnapshot(history.redo(snapshot()))}
            />
          </Tooltip>
          <Button icon={<ShieldCheck size={16} aria-hidden />} loading={validate.isPending} onClick={() => validate.mutate()}>
            Validate
          </Button>
          <Button variant="accent" icon={<Play size={16} aria-hidden />} loading={run.isPending} onClick={() => run.mutate()}>
            Run
          </Button>
        </div>
      }
    >
      {/* The inline-editable name lives in the breadcrumb slot on the real top bar (§15.4); until the
          breadcrumb supports editing it sits here, above the canvas, so renaming is still possible. */}
      <div className="flex min-h-0 flex-1">
        <AgentPalette
          catalog={agents}
          loading={catalog.isPending}
          error={catalog.isError}
          onRetry={() => catalog.refetch()}
          onAdd={(agentType) => addNode(agentType)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-1.5">
            {editingName ? (
              <input
                autoFocus
                value={name}
                maxLength={80}
                onChange={(event) => setName(event.target.value)}
                onBlur={commitName}
                onKeyDown={(event) => {
                  if (event.key === "Enter") commitName();
                  if (event.key === "Escape") {
                    setName(workflow.data?.name ?? "");
                    setEditingName(false);
                  }
                }}
                aria-label="Workflow name"
                className="h-8 rounded-sm border border-border-strong bg-surface px-2 text-body-md font-medium text-text"
              />
            ) : (
              <button type="button" onClick={() => setEditingName(true)} className="text-body-md font-medium text-text hover:underline">
                {name || "Untitled workflow"}
              </button>
            )}
          </div>

          <div ref={wrapper} className="relative min-h-0 flex-1" onDrop={onDrop} onDragOver={(event) => event.preventDefault()}>
            {workflow.isPending ? (
              <div className="grid h-full place-items-center">
                <Spinner label="Loading the workflow" />
              </div>
            ) : (
              <ReactFlow
                nodes={decorated}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeDragStart={() => history.commit(snapshot())}
                onMove={(_event, viewport) => setZoom(viewport.zoom)}
                onInit={() => fitView({ padding: 0.2, maxZoom: 1 })}
                snapToGrid
                snapGrid={[GRID, GRID]}
                deleteKeyCode={["Backspace", "Delete"]}
                onNodesDelete={() => history.commit(snapshot())}
                proOptions={{ hideAttribution: true }}
                fitView
              >
                <Background variant={BackgroundVariant.Dots} gap={GRID} size={1} color="var(--color-canvas-dot)" />
                <Controls showInteractive />
                <MiniMap pannable className="hidden xl:block" />
              </ReactFlow>
            )}

            {/* §15.9 — the canvas is empty and the user needs to know where to start. */}
            {!workflow.isPending && nodes.length === 0 && (
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="grid justify-items-center gap-2 text-center">
                  <p className="text-heading-lg text-text">Start your chain</p>
                  <p className="max-w-[40ch] text-body-md text-text-muted">
                    Drag <strong className="font-medium text-text">Researcher</strong> from the left to begin.
                  </p>
                </div>
              </div>
            )}
          </div>

          <CanvasStatusBar
            steps={nodes.length}
            validation={{
              state: validation ? (validation.valid ? "valid" : "issues") : "unknown",
              count: validation?.issues?.length ?? 0,
              onOpen: () => validate.mutate(),
            }}
            lastRun={null}
            zoom={zoom}
            mockAgents
          />
        </div>
      </div>
    </AppShell>
  );
}

export function CanvasPage() {
  return (
    <ReactFlowProvider>
      <CanvasPageInner />
    </ReactFlowProvider>
  );
}

export type { WorkflowOut };
