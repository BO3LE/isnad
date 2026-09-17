import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Redo2, ShieldCheck, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeTypes,
} from "reactflow";
import { AppShell } from "@/components/app/AppShell";
import { AgentNode, type AgentNodeData, type ConnectHint, type StepData } from "@/components/canvas/AgentNode";
import { AGENT_DRAG_TYPE, AgentPalette } from "@/components/canvas/AgentPalette";
import { CanvasStatusBar } from "@/components/canvas/CanvasStatusBar";
import { HandoverEdge, type HandoverEdgeData } from "@/components/canvas/HandoverEdge";
import { StepDrawer } from "@/components/canvas/StepDrawer";
import { useGraphHistory } from "@/components/canvas/useGraphHistory";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { Button } from "@/design-system/components/Button";
import { IconButton } from "@/design-system/components/IconButton";
import { Spinner } from "@/design-system/components/Progress";
import { Tooltip } from "@/design-system/components/Tooltip";
import { useToast } from "@/design-system/components/toast-context";
import { NotFoundState } from "@/pages/NotFoundPage";
import { ApiError, endpoints, type AgentManifest, type ValidationResult, type WorkflowOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { GRID, graphsEqual, refuseConnection, snapPosition, snapToGrid, stepNumbers, toWorkflowGraph } from "@/lib/graph";
import { describeStep, handover, type StepHandover } from "@/lib/handover";
import { missingSettings, summarise, type Configuration } from "@/lib/schema";

// P-04 · Workflow Canvas (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §15, §21 S-03 · UX-SPEC §4.
// The canvas teaches: each step says what it is set to do and what it still needs, each connection
// names what crosses it, and a step's settings drawer says where every value comes from. All of it
// is worked out from the catalog — no agent is named anywhere in this file (AT-12).

const AUTOSAVE_DELAY = 800; // §15.4
const NODE_WIDTH = 248; // §15.2
const STEP_GAP = 320; // the seeds' spacing: a node and room for the handover label

/** Right of the rightmost step, moved down until it overlaps nothing. */
function nextFreeSpot(taken: { x: number; y: number }[]) {
  const last = taken.reduce((a, b) => (b.x > a.x ? b : a));
  const spot = { x: snapToGrid(last.x + STEP_GAP), y: snapToGrid(last.y) };
  while (taken.some((p) => Math.abs(p.x - spot.x) < NODE_WIDTH && Math.abs(p.y - spot.y) < 128)) spot.y += 160;
  return spot;
}
const nodeTypes: NodeTypes = { agent: AgentNode };
const edgeTypes: EdgeTypes = { handover: HandoverEdge };
const EDGE_DEFAULTS = {
  type: "handover",
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
} as const;

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved"; at: number } | { kind: "error" };

function CanvasPageInner() {
  const { workflowId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { screenToFlowPosition, getViewport, fitView, setCenter } = useReactFlow();

  const userEmail = useAuth((state) => state.email);
  const [nodes, setNodes, onNodesChange] = useNodesState<StepData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [zoom, setZoom] = useState(1);
  const [name, setName] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const history = useGraphHistory<StepData>({ nodes: [], edges: [] });
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
  const catalog = useQuery({
    queryKey: ["catalog"],
    queryFn: endpoints.catalog,
  });

  const agents: AgentManifest[] = useMemo(() => catalog.data ?? [], [catalog.data]);

  // ---------------------------------------------------------------- load
  useEffect(() => {
    const data = workflow.data;
    if (!data || loadedGraph.current === data.id) return;
    loadedGraph.current = data.id;
    setName(data.name);

    const loadedNodes: Node<StepData>[] = (data.graph?.nodes ?? []).map((node) => ({
      id: node.id,
      type: "agent",
      position: snapPosition(node.position),
      data: {
        agentType: node.agent_type,
        requiresApproval: node.requires_approval ?? false,
        configuration: (node.configuration ?? {}) as Configuration,
      },
    }));
    const loadedEdges: Edge[] = (data.graph?.edges ?? []).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...EDGE_DEFAULTS,
    }));

    setNodes(loadedNodes);
    setEdges(loadedEdges);
    // Normalise through the same function the autosave comparison uses, or the first comparison
    // always differs and the canvas saves a graph nobody touched. The baseline holds the snapped
    // positions, so an off-grid stored graph is only rewritten when the user actually edits it.
    savedGraph.current = toWorkflowGraph(loadedNodes, loadedEdges);
    history.reset();
  }, [workflow.data, setNodes, setEdges, history]);

  // Titles and icons come from the catalog, which may arrive after the graph.
  const steps = useMemo(() => stepNumbers(nodes.map((n) => n.id), edges), [nodes, edges]);
  const issuesByNode = useMemo(() => {
    const map = new Map<string, ValidationResult["issues"]>();
    for (const issue of validation?.issues ?? []) {
      if (issue.node_id) map.set(issue.node_id, [...(map.get(issue.node_id) ?? []), issue]);
    }
    return map;
  }, [validation]);

  // UX-SPEC §2 — for every step, where each of its values will come from.
  const handovers = useMemo(() => {
    const stepList = nodes.map((n) => ({ id: n.id, agentType: n.data.agentType, configuration: n.data.configuration }));
    return new Map<string, StepHandover>(stepList.map((step) => [step.id, describeStep(step, stepList, edges, agents)]));
  }, [nodes, edges, agents]);

  const typeOf = useCallback((id: string) => nodes.find((n) => n.id === id)?.data.agentType ?? "", [nodes]);

  const decorated: Node<AgentNodeData>[] = useMemo(
    () =>
      nodes.map((node) => {
        const manifest = agents.find((a) => a.name === node.data.agentType);
        const missing = missingSettings(node.data.configuration, manifest?.config_schema).map((f) => f.key.replace(/_/g, " "));
        const problems = [
          ...(manifest && missing.length > 0 ? [`Missing: ${missing.join(", ")}`] : []),
          ...(handovers.get(node.id)?.needs ?? []),
        ];
        let connectHint: ConnectHint | undefined;
        if (connectingFrom && connectingFrom !== node.id && agents.length > 0) {
          const items = handover(typeOf(connectingFrom), node.data.agentType, agents);
          connectHint = items.length > 0 ? { kind: "takes", items } : { kind: "nothing", from: agentTitle(typeOf(connectingFrom), agents) };
        }
        return {
          ...node,
          selected: node.id === selectedId,
          data: {
            ...node.data,
            requiresApproval: manifest?.requires_approval === true || node.data.requiresApproval,
            title: agentTitle(node.data.agentType, agents),
            icon: manifest?.icon,
            family: manifest?.family,
            // Only a connected step has a place in the chain (UX-SPEC §4.2).
            step: edges.some((e) => e.source === node.id || e.target === node.id) ? steps.get(node.id) : undefined,
            summary: summarise(node.data.configuration, manifest?.config_schema),
            problems,
            issueCount: issuesByNode.get(node.id)?.length ?? 0,
            connectHint,
          },
        };
      }),
    [nodes, edges, agents, steps, issuesByNode, handovers, connectingFrom, selectedId, typeOf],
  );

  // UX-SPEC §4.3 — each connection names what crosses it.
  const decoratedEdges: Edge<HandoverEdgeData>[] = useMemo(
    () =>
      agents.length === 0
        ? edges
        : edges.map((edge) => ({
            ...edge,
            ...EDGE_DEFAULTS,
            data: {
              items: handover(typeOf(edge.source), typeOf(edge.target), agents),
              targetTitle: agentTitle(typeOf(edge.target), agents),
              emphasised: [edge.id, edge.source, edge.target].some((id) => id === hovered || id === selectedId),
            },
          })),
    [edges, agents, typeOf, hovered, selectedId],
  );

  // ---------------------------------------------------------------- autosave (§15.4)
  const graph = useMemo(() => toWorkflowGraph(nodes, edges), [nodes, edges]);

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
  const dragStart = useRef<ReturnType<typeof snapshot> | null>(null);

  const addNode = useCallback(
    (agentType: string, at?: { x: number; y: number }) => {
      const manifest = agents.find((a) => a.name === agentType);
      let position: { x: number; y: number };
      if (at) {
        position = { x: snapToGrid(at.x), y: snapToGrid(at.y) };
      } else if (nodes.length > 0) {
        // From the palette: after the chain's last step, where it reads as "next", then shown.
        position = nextFreeSpot(nodes.map((n) => n.position));
        reveal.current = position;
      } else {
        const box = wrapper.current?.getBoundingClientRect();
        const centre = screenToFlowPosition({
          x: (box?.left ?? 0) + (box?.width ?? 800) / 2,
          y: (box?.top ?? 0) + (box?.height ?? 600) / 2,
        });
        position = {
          x: snapToGrid(centre.x - NODE_WIDTH / 2),
          y: snapToGrid(centre.y - 48),
        };
      }

      history.commit(snapshot());
      const id = crypto.randomUUID();
      setNodes((current) => [
        ...current,
        {
          id,
          type: "agent",
          position,
          data: {
            agentType,
            // D-08: Distribute agents always require approval, and the catalog is what says so.
            requiresApproval: manifest?.requires_approval ?? false,
            // Empty on purpose: a new step holds only what the user chooses (UX-SPEC §4.5).
            configuration: {},
          },
        },
      ]);
      // A new step opens its settings, so the next thing the user sees is what it needs.
      setSelectedId(id);
    },
    [agents, nodes, screenToFlowPosition, history, snapshot, setNodes],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const { source, target } = connection;
      if (!source || !target) return;

      const refusal = refuseConnection(edges, source, target);
      if (refusal === "cycle")
        return toast({
          variant: "error",
          message: "That connection would create a loop.",
        });
      if (refusal === "self")
        return toast({
          variant: "error",
          message: "A step can't feed itself.",
        });
      if (refusal === "duplicate") return;

      history.commit(snapshot());
      setEdges((current) => addEdge({ ...connection, id: `${source}-${target}`, ...EDGE_DEFAULTS }, current));
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

  const updateStep = useCallback(
    (id: string, patch: Partial<StepData>) =>
      setNodes((current) => current.map((node) => (node.id === id ? { ...node, data: { ...node.data, ...patch } } : node))),
    [setNodes],
  );

  const applySnapshot = useCallback(
    (next: { nodes: Node<StepData>[]; edges: Edge[] } | null) => {
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

  const closeDrawer = useCallback(() => setSelectedId(null), []);

  // Show a step added from the palette. Wait a frame so the settings drawer, which opens at the
  // same time, has already narrowed the canvas — otherwise the step is centred behind it.
  const reveal = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    const target = reveal.current;
    if (!target) return;
    reveal.current = null;
    const frame = window.requestAnimationFrame(() =>
      setCenter(target.x + NODE_WIDTH / 2, target.y + 48, {
        zoom: getViewport().zoom,
        duration: 200,
      }),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [nodes, setCenter, getViewport]);

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

  const selectedStep = decorated.find((node) => node.id === selectedId && handovers.has(node.id));

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
          <div className="hidden items-center gap-2 sm:flex">
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
          </div>
          <Button
            icon={<ShieldCheck size={16} aria-hidden />}
            aria-label="Validate"
            loading={validate.isPending}
            onClick={() => validate.mutate()}
            className="gap-2"
          >
            <span className="hidden sm:inline">Validate</span>
          </Button>
          <Button variant="accent" icon={<Play size={16} aria-hidden />} loading={run.isPending} onClick={() => run.mutate()}>
            Run
          </Button>
        </div>
      }
    >
      {/* The inline-editable name lives in the breadcrumb slot on the real top bar (§15.4); until the
          breadcrumb supports editing it sits here, above the canvas, so renaming is still possible. */}
      <div className="relative flex min-h-0 flex-1">
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
                edges={decoratedEdges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onNodeClick={(_event, node) => setSelectedId(node.id)}
                onPaneClick={() => setSelectedId(null)}
                onNodeMouseEnter={(_event, node) => setHovered(node.id)}
                onNodeMouseLeave={() => setHovered(null)}
                onEdgeMouseEnter={(_event, edge) => setHovered(edge.id)}
                onEdgeMouseLeave={() => setHovered(null)}
                onConnectStart={(_event, params) => setConnectingFrom(params.handleType === "source" ? params.nodeId : null)}
                onConnectEnd={() => setConnectingFrom(null)}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeDragStart={() => {
                  dragStart.current = snapshot();
                }}
                onNodeDragStop={() => {
                  // A click counts as a drag to React Flow; only a real move is worth an undo step.
                  const before = dragStart.current;
                  dragStart.current = null;
                  if (before && !graphsEqual(toWorkflowGraph(before.nodes, before.edges), graph)) history.commit(before);
                }}
                onMove={(_event, viewport) => setZoom(viewport.zoom)}
                onInit={() => fitView({ padding: 0.2, maxZoom: 1 })}
                snapToGrid
                snapGrid={[GRID, GRID]}
                deleteKeyCode={["Backspace", "Delete"]}
                onNodesDelete={(deleted) => {
                  history.commit(snapshot());
                  if (deleted.some((node) => node.id === selectedId)) setSelectedId(null);
                }}
                proOptions={{ hideAttribution: true }}
                fitView
              >
                <Background variant={BackgroundVariant.Dots} gap={GRID} size={1} color="var(--color-canvas-dot)" />
                <Controls showInteractive />
                <MiniMap
                  pannable
                  className="hidden xl:block"
                  style={{ background: "var(--color-surface)" }}
                  nodeColor="var(--color-border-strong)"
                  maskColor="rgb(11 11 10 / 0.12)"
                />
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

        {selectedStep && (
          <StepDrawer
            stepId={selectedStep.id}
            data={selectedStep.data}
            manifest={agents.find((a) => a.name === selectedStep.data.agentType)}
            catalog={agents}
            handover={handovers.get(selectedStep.id)!}
            issues={issuesByNode.get(selectedStep.id) ?? []}
            saveLabel={saveLabel}
            userEmail={userEmail}
            onBeginEdit={() => history.commit(snapshot())}
            onConfigurationChange={(configuration) => updateStep(selectedStep.id, { configuration })}
            onApprovalChange={(requiresApproval) => updateStep(selectedStep.id, { requiresApproval })}
            onClose={closeDrawer}
          />
        )}
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
