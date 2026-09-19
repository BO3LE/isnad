import { useEffect, useState } from "react";
import { Button } from "@/design-system/components/Button";
import { ProgressBar } from "@/design-system/components/Progress";
import { StatusChip } from "@/design-system/status/StatusChip";
import { rejectedMeta, runStatusMeta } from "@/design-system/status/statusMeta";
import type { RunState, RunStatus } from "@/lib/api";
import { countDone, stepError, type Shown } from "@/lib/runPlayback";

// UX-SPEC §6 — the run header on the canvas. It reassures ("Writer is working"), narrates retries,
// says when a slow step is allowed to be slow, and offers exactly one next action.

const SLOW_AFTER_MS = 10_000;

export interface RunBarProps {
  run: RunState | undefined;
  status: RunStatus | null;
  shown: Shown;
  titleOf: (nodeId: string) => string;
  onCancel: () => void;
  cancelling: boolean;
  onReview: () => void;
  onExit: () => void;
}

function clock(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function spoken(ms: number): string {
  const seconds = Math.max(1, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function RunBar({ run, status, shown, titleOf, onCancel, cancelling, onReview, onExit }: RunBarProps) {
  const [now, setNow] = useState(() => Date.now());
  const finished = status === "succeeded" || status === "failed" || status === "cancelled";

  useEffect(() => {
    if (finished) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [finished]);

  const nodes = run?.nodes ?? [];
  const total = run?.total_nodes ?? nodes.length;
  const done = countDone(shown);
  const startedAt = Date.parse(run?.started_at ?? run?.created_at ?? "") || now;
  const endedAt = finished && run?.completed_at ? Date.parse(run.completed_at) : now;

  const current = nodes.find((node) => ["running", "retrying"].includes(shown[node.node_id] ?? ""));
  const waiting = nodes.find((node) => shown[node.node_id] === "awaiting_approval");
  const failedNode = nodes.find((node) => node.status === "failed");

  const rejected = status === "failed" && stepError(failedNode?.error_message)?.rejected === true;

  let message: string;
  if (!status || status === "queued") message = "Queued — starting in a moment…";
  else if (status === "awaiting_approval" && waiting) message = `${titleOf(waiting.node_id)} is waiting for your approval. Nothing has been sent yet.`;
  else if (status === "succeeded") message = `Run finished in ${spoken(endedAt - startedAt)}.`;
  else if (status === "cancelled") message = "Run cancelled. Steps that hadn't started were skipped.";
  else if (status === "failed" && failedNode) {
    const error = stepError(failedNode.error_message);
    message = error?.rejected
      ? `Rejected by you at ${titleOf(failedNode.node_id)}. The steps after it didn't run.`
      : `Run stopped at ${titleOf(failedNode.node_id)}. ${error?.text ?? ""}`.trim();
  }
  else if (current && shown[current.node_id] === "retrying")
    message = `${titleOf(current.node_id)}: attempt ${current.retry_count} failed. Trying again…`;
  else if (current) {
    const since = current.started_at ? now - Date.parse(current.started_at) : 0;
    message =
      since > SLOW_AFTER_MS
        ? `${titleOf(current.node_id)} is still working — this step can take a few minutes. You can leave this page.`
        : `${titleOf(current.node_id)} is working…`;
  } else message = "Handing over to the next step…";

  const tone = rejected ? "approval" : status === "succeeded" ? "success" : status === "failed" ? "failed" : status === "awaiting_approval" ? "approval" : "running";

  return (
    <section
      className="flex min-h-10 shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-t border-border bg-surface px-3 py-1.5 text-body-sm"
      aria-label="Run progress"
    >
      <StatusChip meta={rejected ? rejectedMeta : runStatusMeta[status ?? "queued"]} />
      <span className="font-mono text-mono-sm tabular-nums text-text-muted">{clock(endedAt - startedAt)}</span>
      <ProgressBar label="Steps finished" value={total ? done / total : 0} tone={tone} className="w-24 sm:w-40" />
      <span className="font-mono text-mono-sm tabular-nums text-text-muted">
        {done} of {total} steps
      </span>
      <p className="min-w-0 flex-1 truncate text-text" aria-live="polite" title={message}>
        {message}
      </p>
      {status === "awaiting_approval" && (
        <Button variant="primary" size="sm" onClick={onReview}>
          Review
        </Button>
      )}
      {!finished && (
        <Button size="sm" onClick={onCancel} loading={cancelling}>
          Cancel run
        </Button>
      )}
      {finished && (
        <Button size="sm" onClick={onExit}>
          Back to editing
        </Button>
      )}
    </section>
  );
}
