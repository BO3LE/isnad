import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { endpoints } from "@/lib/api";

// The data behind S-04's "Last output" tab (DESIGN-SYSTEM §21 S-04, §17.6): what this step produced
// the last time the workflow ran. Its own module because StepDrawer needs the answer before it can
// decide whether to offer the tab at all, and a file exporting both a hook and a component loses
// fast refresh.

/**
 * This step's outputs from the workflow's most recent run.
 *
 * Both queries share their keys with the canvas (`workflow-runs`) and the approval preview
 * (`run-outputs`), so neither is refetched from scratch. Two things that share is NOT doing, both
 * measured rather than assumed:
 * - The drawer still revalidates on mount — React Query's default `staleTime` is 0 — so this saves
 *   the wait, not the request. That is the right trade: the tab claims "the most recent run", and
 *   a stale list would answer with an out-of-date one.
 * - Only the runs half is warm on the canvas. `run-outputs` is usually not, so on the first open
 *   for a run the drawer paints with Settings alone and the second tab appears when the outputs
 *   land. Withholding it is deliberate (§17.6 — the tab exists only if an output does); the cost
 *   is that the tab row grows a moment after the drawer opens.
 *
 * A failure to load is silent: no tab, no message, the same as a step that produced nothing. The
 * drawer is for settings, and a step's last output is a look-up, not something worth an error over
 * a form someone came here to fill in.
 */
export function useLastOutput(workflowId: string, stepId: string) {
  const runs = useQuery({
    queryKey: ["workflow-runs", workflowId],
    queryFn: () => endpoints.workflowRuns(workflowId),
    enabled: Boolean(workflowId),
  });

  // §21 S-04 says "the most recent run", not "the most recent run that reached this step" — a step
  // that produced nothing this time reads as nothing, rather than quietly showing last week's file.
  // (§15.8's context-menu entry says "a previous run" instead; the tab follows S-04, which is the
  // section that describes it.)
  const lastRun = runs.data?.[0] ?? null;

  const outputs = useQuery({
    queryKey: ["run-outputs", lastRun?.id ?? null],
    queryFn: () => endpoints.runOutputs(lastRun!.id),
    enabled: lastRun !== null,
  });

  const mine = useMemo(() => (outputs.data ?? []).filter((output) => output.node_id === stepId), [outputs.data, stepId]);

  return {
    outputs: mine,
    ranAt: lastRun?.created_at ?? null,
    // Pending only while something is actually in flight. A workflow with no runs is not pending:
    // there is nothing left to wait for, and saying otherwise would hide the tab for good. (The
    // canvas always has a workflow id, so the disabled-`runs` case does not arise here.)
    isPending: runs.isPending || (lastRun !== null && outputs.isPending),
    isError: runs.isError || outputs.isError,
  };
}

export type LastOutputState = ReturnType<typeof useLastOutput>;
