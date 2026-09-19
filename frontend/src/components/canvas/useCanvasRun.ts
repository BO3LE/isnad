import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { endpoints } from "@/lib/api";
import { TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { ACTIVE_RUN, PLAYBACK_TICK_MS, advance, caughtUp, serverStatuses, shownRunStatus, type Shown } from "@/lib/runPlayback";

// The run the canvas is showing (UX-SPEC §6: the canvas is where you watch). Polls the run, plays
// its progress forward one handover at a time, and picks up a run that was already going when the
// page opened — so a run waiting for approval is waiting on the canvas, not somewhere else.

const POLL_MS = 1000;

export function useCanvasRun(workflowId: string) {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const [shown, setShown] = useState<Shown>({});
  const adopted = useRef(false);

  const history = useQuery({
    queryKey: ["workflow-runs", workflowId],
    queryFn: () => endpoints.workflowRuns(workflowId),
    enabled: Boolean(workflowId),
  });

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => endpoints.runState(runId!),
    enabled: runId !== null,
    refetchInterval: (query) => (query.state.data && TERMINAL_RUN_STATUSES.has(query.state.data.status) ? false : POLL_MS),
    // Keep watching from another tab: the title is how a user there learns a step needs them (§16.6).
    refetchIntervalInBackground: true,
  });

  // A run already under way when the page opened is shown as it stands, not replayed.
  useEffect(() => {
    if (adopted.current || !history.data) return;
    adopted.current = true;
    const active = history.data.find((summary) => ACTIVE_RUN.has(summary.status));
    if (!active) return;
    setRunId(active.id);
    endpoints
      .runState(active.id)
      .then((state) => setShown(serverStatuses(state)))
      .catch(() => undefined);
  }, [history.data]);

  const server = useMemo(() => serverStatuses(run.data), [run.data]);
  const order = useMemo(() => (run.data?.nodes ?? []).map((node) => node.node_id), [run.data]);

  // Cancelling is the user's own action: show it at once.
  useEffect(() => {
    if (run.data?.status === "cancelled") setShown(server);
  }, [run.data?.status, server]);

  useEffect(() => {
    if (runId === null || caughtUp(shown, server)) return;
    const timer = window.setTimeout(() => setShown((current) => advance(current, server, order)), PLAYBACK_TICK_MS);
    return () => window.clearTimeout(timer);
  }, [runId, shown, server, order]);

  const start = useCallback(
    (id: string) => {
      adopted.current = true;
      setShown({});
      setRunId(id);
      queryClient.invalidateQueries({ queryKey: ["workflow-runs", workflowId] });
    },
    [queryClient, workflowId],
  );

  const exit = useCallback(() => {
    setRunId(null);
    setShown({});
    queryClient.invalidateQueries({ queryKey: ["workflow-runs", workflowId] });
    queryClient.invalidateQueries({ queryKey: ["workflows"] });
  }, [queryClient, workflowId]);

  const refresh = useCallback(() => queryClient.invalidateQueries({ queryKey: ["run", runId] }), [queryClient, runId]);

  return {
    runId,
    run: run.data,
    shown,
    status: shownRunStatus(run.data, shown),
    lastRun: history.data?.[0] ?? null,
    start,
    exit,
    refresh,
  };
}

export type CanvasRun = ReturnType<typeof useCanvasRun>;
