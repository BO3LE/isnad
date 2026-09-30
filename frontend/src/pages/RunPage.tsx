import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
import { RunTabs } from "@/components/runs/RunTabs";
import { StepList } from "@/components/runs/StepList";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { ProgressBar } from "@/design-system/components/Progress";
import { Skeleton } from "@/design-system/components/Skeleton";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta, TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { formatAbsoluteTime, pluralise } from "@/lib/format";
import { stepError } from "@/lib/runPlayback";
import { ApiError, endpoints, type RunState } from "@/lib/api";
import { useToast } from "@/design-system/components/toast-context";
import { NotFoundState } from "@/pages/NotFoundPage";

const POLL_MS = 2000;
function ReviewLink({ workflowId }: { workflowId: string }) { return <Link to={`/workflows/${workflowId}`} className="inline-flex h-7 items-center rounded-sm bg-surface-inverse px-2.5 text-caption text-text-inverse">Review</Link>; }
function elapsedMs(run: RunState, now: number) { const from = run.started_at ?? run.created_at; return from ? Math.max(0, (run.completed_at ? Date.parse(run.completed_at) : now) - Date.parse(from)) : 0; }
function clock(ms: number) { const seconds = Math.floor(ms / 1000); return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`; }

export function RunPage() {
  const { runId = "" } = useParams(); const queryClient = useQueryClient(); const [now, setNow] = useState(() => Date.now()); const toast = useToast();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => endpoints.runState(runId), retry: (count, error) => !("status" in error && error.status === 404) && count < 3, refetchInterval: (q) => q.state.data && TERMINAL_RUN_STATUSES.has(q.state.data.status) ? false : POLL_MS, refetchIntervalInBackground: true });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog, staleTime: 300000 }); const state = run.data; const live = state != null && !TERMINAL_RUN_STATUSES.has(state.status);
  useEffect(() => { if (!live) return; const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, [live]);
  const cancel = useMutation({ mutationFn: () => endpoints.cancel(runId), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", runId] }), onError: (error) => toast({ variant: "error", message: error instanceof ApiError ? error.message : "Couldn't cancel the run." }) });
  const steps = state?.nodes ?? []; const done = steps.filter((s) => s.status === "success").length; const total = state?.total_nodes || steps.length; const waiting = steps.find((s) => s.status === "awaiting_approval"); const failed = steps.find((s) => s.status === "failed"); const failure = stepError(failed?.error_message); const titleOf = (type: string) => catalog.data ? agentTitle(type, catalog.data) : "This step";
  if (run.isError && "status" in run.error && run.error.status === 404) return <NotFoundState message="That run doesn't exist." />;
  return <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Run" }]}><PageBody width="narrow">
    {run.isPending && <div className="grid gap-3" aria-busy><Skeleton className="h-8 w-64" /><Skeleton className="h-24 w-full" /></div>}
    {run.isError && !("status" in run.error && run.error.status === 404) && <Banner variant="error">Couldn't load this run. {run.error.message}</Banner>}
    {state && <div className="grid gap-5"><header className="grid gap-3"><div className="flex flex-wrap items-center gap-3"><h1 className="text-heading-lg text-text">Run</h1><StatusChip meta={runStatusMeta[state.status]} />{state.created_at && <span className="text-body-sm text-text-muted">{formatAbsoluteTime(state.created_at)}</span>}{live && <Button className="ml-auto" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel run</Button>}</div><div className="flex gap-3"><ProgressBar value={total ? done / total : 0} label="Steps finished" tone={state.status === "failed" ? "failed" : state.status === "succeeded" ? "success" : "running"} className="w-40" /><span>{done} of {pluralise(total, "step")}</span><span>{clock(elapsedMs(state, now))}</span></div>{state.status === "succeeded" && <Banner variant="neutral">Every step finished.</Banner>}<RunTabs runId={state.id} current="overview" /></header>
      {waiting && <Banner variant="approval" action={<ReviewLink workflowId={state.workflow_id} />}>{titleOf(waiting.agent_type)} is waiting for your approval. Nothing has been sent yet.</Banner>}
      {state.status === "failed" && failed && <Banner variant="error">Run stopped at {titleOf(failed.agent_type)}. {failure?.text}</Banner>}
      {!live && <Link to={`/runs/${runId}/outputs`} className="text-text underline">See what this run made</Link>}
      <section aria-label="Steps" className="grid gap-3"><h2 className="text-heading-sm text-text">Steps</h2><StepList steps={steps} agents={catalog.data} actionFor={(step) => step.status === "awaiting_approval" ? <ReviewLink workflowId={state.workflow_id} /> : null} /></section>
    </div>}
  </PageBody></AppShell>;
}
