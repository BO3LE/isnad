import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
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
import { endpoints, type RunState } from "@/lib/api";
import { NotFoundState } from "@/pages/NotFoundPage";

// P-06, the run monitor (DESIGN-SYSTEM §21 S-05). The canvas is where a run is watched while you
// are sitting in front of it; this page is how a run is reached any other way — a deep link, the
// next morning, or from a phone. It is deliberately not a diagram: the steps list is the whole run
// (§22 puts the list first on narrow screens, and it is the accessible alternative everywhere).
//
// The read-only canvas the spec pairs with the list is not built here: `RunState` carries no graph
// — no edges and no positions — so the only graph available is the workflow's *current* one, which
// may have been edited since. Drawing that as if it were this run would misreport it.

const POLL_MS = 2000;

/** Approving happens on the canvas, where the run is shown with what each step is about to send. */
function ReviewLink({ workflowId }: { workflowId: string }) {
  return (
    <Link
      to={`/workflows/${workflowId}`}
      /* Matches Button's primary/sm, because it is a link doing a button's job. */
      className="inline-flex h-7 items-center justify-center gap-1.5 whitespace-nowrap rounded-sm bg-surface-inverse px-2.5 text-caption text-text-inverse transition-opacity duration-100 ease-standard hover:opacity-90 hover:no-underline active:translate-y-px"
    >
      Review
    </Link>
  );
}

function elapsedMs(run: RunState, now: number): number {
  const from = run.started_at ?? run.created_at;
  if (!from) return 0;
  const end = run.completed_at ? Date.parse(run.completed_at) : now;
  return Math.max(0, end - Date.parse(from));
}

function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function RunPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const [now, setNow] = useState(() => Date.now());

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => endpoints.runState(runId),
    retry: (count, error) => !("status" in error && error.status === 404) && count < 3,
    refetchInterval: (query) => (query.state.data && TERMINAL_RUN_STATUSES.has(query.state.data.status) ? false : POLL_MS),
    // §16.6 — someone watching from another tab still sees it finish.
    refetchIntervalInBackground: true,
  });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog, staleTime: 5 * 60_000 });

  const state = run.data;
  const live = state != null && !TERMINAL_RUN_STATUSES.has(state.status);

  // The elapsed time has to tick without the server saying anything.
  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["run", runId] });
  const cancel = useMutation({ mutationFn: () => endpoints.cancel(runId), onSuccess: refresh });

  const steps = state?.nodes ?? [];
  const done = steps.filter((s) => s.status === "success").length;
  const total = state?.total_nodes || steps.length;
  const waiting = steps.find((s) => s.status === "awaiting_approval");
  const failed = steps.find((s) => s.status === "failed");
  const failure = stepError(failed?.error_message);
  const titleOf = (agentType: string) => agentTitle(agentType, catalog.data);

  // §16.6 — the tab says what the run needs, for a user who is somewhere else.
  useEffect(() => {
    if (!state) return;
    const prefix = state.status === "awaiting_approval" ? "✋ Needs approval · " : live ? "● Running · " : "";
    document.title = `${prefix}Run · Isnad`;
    return () => {
      document.title = "Isnad";
    };
  }, [state, live]);

  if (run.isError && "status" in run.error && run.error.status === 404) {
    return <NotFoundState message="That run doesn't exist." />;
  }

  return (
    <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Run" }]}>
      <PageBody width="narrow">
        {run.isPending && (
          <div className="grid gap-3" aria-busy>
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {run.isError && !("status" in run.error && run.error.status === 404) && (
          <Banner variant="error">Couldn't load this run. {run.error.message}</Banner>
        )}

        {state && (
          <div className="grid gap-5">
            <header className="grid gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-heading-lg text-text">Run</h1>
                <StatusChip meta={runStatusMeta[state.status]} />
                {state.created_at && (
                  <span className="text-body-sm text-text-muted">{formatAbsoluteTime(state.created_at)}</span>
                )}
                {live && (
                  <Button
                    className="ml-auto"
                    onClick={() => cancel.mutate()}
                    loading={cancel.isPending}
                    disabled={state.status === "queued"}
                  >
                    Cancel run
                  </Button>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <ProgressBar
                  value={total > 0 ? done / total : 0}
                  label="Steps finished"
                  tone={state.status === "failed" ? "failed" : state.status === "succeeded" ? "success" : "running"}
                  className="w-40"
                />
                <span className="font-mono text-mono-sm tabular-nums text-text-muted">
                  {done} of {pluralise(total, "step")}
                </span>
                <span className="font-mono text-mono-sm tabular-nums text-text-muted">{clock(elapsedMs(state, now))}</span>
              </div>

              {/* One line saying where the run is, announced as it changes. The banners below are
                  themselves live regions, so when one of them is carrying the news this line would
                  say it a second time — to a screen reader as much as on screen. */}
              {!waiting && state.status !== "failed" && (
                <p aria-live="polite" className="text-body-md text-text-muted">
                  {state.status === "succeeded"
                    ? "Every step finished."
                    : state.status === "cancelled"
                      ? "Run cancelled. Steps that hadn't started were skipped."
                      : state.status === "queued"
                        ? "Waiting for a worker to pick this up."
                        : `${pluralise(done, "step")} of ${total} finished.`}
                </p>
              )}
            </header>

            {waiting && (
              <Banner
                variant="approval"
                action={<ReviewLink workflowId={state.workflow_id} />}
              >
                {titleOf(waiting.agent_type)} is waiting for your approval. Nothing has been sent yet.
              </Banner>
            )}

            {/* A rejection is the user's own decision and never reads as a failure (§2 rule 7). */}
            {state.status === "failed" && failed && !failure?.rejected && (
              <Banner variant="error">
                Run stopped at {titleOf(failed.agent_type)}. {failure?.text}
              </Banner>
            )}
            {state.status === "failed" && failure?.rejected && (
              <Banner variant="info">You rejected {failed ? titleOf(failed.agent_type) : "a step"}. Nothing was sent.</Banner>
            )}

            <section aria-label="Steps" className="grid gap-3">
              <h2 className="text-heading-sm text-text">Steps</h2>
              <StepList
                steps={steps}
                agents={catalog.data}
                actionFor={(step) =>
                  step.status === "awaiting_approval" ? <ReviewLink workflowId={state.workflow_id} /> : null
                }
              />
            </section>
          </div>
        )}
      </PageBody>
    </AppShell>
  );
}
