import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { Skeleton } from "@/design-system/components/Skeleton";
import { agentTitle, manifestFor } from "@/design-system/agents/agentMeta";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta, rejectedMeta } from "@/design-system/status/statusMeta";
import { formatAbsoluteTime, formatDuration } from "@/lib/format";
import { retryLabel } from "@/lib/logs";
import { stepError } from "@/lib/runPlayback";
import type { AgentManifest, NodeState } from "@/lib/api";

// DESIGN-SYSTEM.md §21 S-05 — "the accessible alternative to the canvas". The whole run has to be
// followable here: a person who never sees the diagram must still know what each step is, what
// state it is in, how long it took, how many attempts it needed and why it stopped.
//
// Everything comes from the run and the catalog, so a seventh agent lists itself (AT-12).

export interface StepListProps {
  steps: NodeState[];
  agents?: AgentManifest[];
  /** Rendered inside the row that is waiting for a person. */
  actionFor?: (step: NodeState) => React.ReactNode;
}

function attempts(step: NodeState): string | null {
  if (step.retry_count < 1) return null;
  // While it is between attempts the node and this row say the same thing (§16.5). Afterwards the
  // useful number is how many tries it took, which is the retries plus the first attempt.
  return step.status === "retrying" ? retryLabel(step.retry_count) : `Took ${step.retry_count + 1} attempts`;
}

export function StepList({ steps, agents, actionFor }: StepListProps) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <ol className="grid gap-2">
      {steps.map((step, index) => {
        // Until the catalog arrives the agent's own name and glyph are unknown. The placeholder
        // glyph means "no agent is installed for this", and the raw type reads "publisher" where
        // the product says "Publisher" — so neither is shown as if it were the answer.
        const known = agents !== undefined;
        const manifest = manifestFor(step.agent_type, agents);
        const title = agentTitle(step.agent_type, agents);
        const error = stepError(step.error_message);
        const tries = attempts(step);
        // A row opens only when it has something more to say than the summary already shows.
        const detail = error || tries || step.started_at;
        const expanded = open === step.node_id;

        return (
          <li key={step.node_id} className="rounded-md border border-border bg-surface shadow-1">
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="font-mono text-mono-sm text-text-muted" aria-hidden>
                {index + 1}
              </span>
              {known ? (
                <AgentIcon icon={manifest?.icon} family={manifest?.family} size="sm" />
              ) : (
                <Skeleton className="h-6 w-6 rounded-xs" />
              )}
              <span className="text-body-md font-medium text-text">
                <span className="sr-only">Step {index + 1}: </span>
                {known ? title : <Skeleton className="inline-block h-4 w-20 align-middle" />}
              </span>
              <StatusChip meta={error?.rejected ? rejectedMeta : nodeStatusMeta[step.status]} />
              {step.duration_ms != null && (
                <span className="font-mono text-mono-sm text-text-muted">{formatDuration(step.duration_ms / 1000)}</span>
              )}
              <span className="flex-1" />
              {actionFor?.(step)}
              {detail && (
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={`step-detail-${step.node_id}`}
                  onClick={() => setOpen(expanded ? null : step.node_id)}
                  className="flex items-center gap-1 rounded-xs text-body-sm text-text-muted hover:text-text"
                >
                  <ChevronRight size={14} aria-hidden className={expanded ? "rotate-90 transition-transform" : "transition-transform"} />
                  {expanded ? "Hide details" : "Details"}
                  <span className="sr-only"> for {title}</span>
                </button>
              )}
            </div>

            {/* The reason a step stopped is the most important thing on the row, so it is never
                hidden behind the toggle — only the timings are. */}
            {error && (
              <p className={`border-t border-border px-4 py-2 text-body-sm ${error.rejected ? "text-text-muted" : "text-status-failed-fg"}`}>
                {error.rejected ? "You rejected this step. Nothing was sent." : error.text}
              </p>
            )}

            {expanded && (
              <dl
                id={`step-detail-${step.node_id}`}
                className="grid gap-1 border-t border-border px-4 py-3 text-body-sm sm:grid-cols-[auto_1fr] sm:gap-x-4"
              >
                {tries && (
                  <>
                    <dt className="text-text-muted">Attempts</dt>
                    <dd className="text-text">{tries}</dd>
                  </>
                )}
                {step.started_at && (
                  <>
                    <dt className="text-text-muted">Started</dt>
                    <dd className="text-text">{formatAbsoluteTime(step.started_at)}</dd>
                  </>
                )}
                {step.completed_at && (
                  <>
                    <dt className="text-text-muted">Finished</dt>
                    <dd className="text-text">{formatAbsoluteTime(step.completed_at)}</dd>
                  </>
                )}
              </dl>
            )}
          </li>
        );
      })}
    </ol>
  );
}
