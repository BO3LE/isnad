import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/design-system/components/Button";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta, runStatusMeta, TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { endpoints } from "@/lib/api";

// S-05 skeleton (DESIGN-SYSTEM.md §21). Polls every 2 s (GP-plan W3 allows this before Realtime).
// TODO(W3, Ahmed): run header, read-only canvas, retry strip; TODO(W7): approval screen S-06.
export function RunPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => endpoints.runState(runId),
    refetchInterval: (query) => (query.state.data && TERMINAL_RUN_STATUSES.has(query.state.data.status) ? false : 2000),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["run", runId] });
  const approve = useMutation({ mutationFn: (nodeId: string) => endpoints.approve(runId, nodeId, "approve"), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: () => endpoints.cancel(runId), onSuccess: refresh });

  const state = run.data;
  const done = state?.nodes?.filter((n) => n.status === "success").length ?? 0;

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <span className="text-body-md text-text-muted">
          Run <span className="font-mono text-mono-sm">{runId.slice(0, 8)}</span>
        </span>
      </TopBar>
      <main className="mx-auto grid w-full max-w-[960px] gap-6 px-4 py-8 md:px-8">
        {run.isError && <p role="alert" className="text-status-failed-fg">{run.error.message}</p>}
        {state && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-heading-lg">Run</h1>
              <StatusChip meta={runStatusMeta[state.status]} />
              <span className="font-mono text-mono-sm text-text-muted">
                {done} of {state.total_nodes} steps
              </span>
              {!TERMINAL_RUN_STATUSES.has(state.status) && (
                <Button className="ml-auto" onClick={() => cancel.mutate()} loading={cancel.isPending}>
                  Cancel run
                </Button>
              )}
            </div>
            <ol className="grid gap-2" aria-live="polite">
              {state.nodes?.map((node, i) => (
                <li key={node.node_id} className="grid gap-2 rounded-md border border-border bg-surface p-4 shadow-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-mono-sm text-text-muted">{i + 1}</span>
                    <span className="text-body-md font-medium capitalize">{node.agent_type}</span>
                    <StatusChip
                      meta={nodeStatusMeta[node.status]}
                      label={node.status === "retrying" ? `Retrying ${node.retry_count}/3` : undefined}
                    />
                    {node.duration_ms != null && (
                      <span className="ml-auto font-mono text-mono-sm text-text-muted">{(node.duration_ms / 1000).toFixed(1)} s</span>
                    )}
                    {node.status === "awaiting_approval" && (
                      <Button variant="primary" size="sm" className="ml-auto" onClick={() => approve.mutate(node.node_id)} loading={approve.isPending}>
                        Approve
                      </Button>
                    )}
                  </div>
                  {node.error_message && <pre className="whitespace-pre-wrap font-mono text-mono-sm text-status-failed-fg">{node.error_message}</pre>}
                </li>
              ))}
            </ol>
          </>
        )}
      </main>
    </div>
  );
}
