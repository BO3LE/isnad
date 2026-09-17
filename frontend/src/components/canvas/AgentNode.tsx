import { ArrowRightToLine, CircleAlert } from "lucide-react";
import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta } from "@/design-system/status/statusMeta";
import type { NodeStatus } from "@/lib/api";
import type { Configuration } from "@/lib/schema";

// DESIGN-SYSTEM.md §15.2 — "the most important component in the product" — and UX-SPEC §4.2:
// the node is where the canvas teaches. It says what the step is set to do, what it is still
// missing, and, while a connection is being drawn, what it would take from the other end.

/** What the canvas stores for a step. Everything else on the node is worked out from it. */
export interface StepData {
  agentType: string;
  configuration: Configuration;
  requiresApproval: boolean;
}

/** While a connection is being drawn, from the point of view of each possible target. */
export type ConnectHint = { kind: "takes"; items: string[] } | { kind: "nothing"; from: string };

export interface AgentNodeData extends StepData {
  title: string;
  icon?: string | null;
  family?: string | null;
  step?: number;
  /** "5 sources", "Short", "1 recipient" — labels, never raw values. */
  summary: string[];
  /** "Missing: topic", "Needs a Researcher before this step". */
  problems: string[];
  /** Set once /validate has run; a dashed red border and a count (§15.2 invalid state). */
  issueCount?: number;
  connectHint?: ConnectHint;
  /** Live status during a run; absent in edit mode, where no chip is shown. */
  status?: NodeStatus;
  readOnly?: boolean;
}

const HANDLE = "!h-2.5 !w-2.5 !border-[1.5px] !border-border-strong !bg-surface";

export const AgentNode = memo(function AgentNode({ data, selected }: NodeProps<AgentNodeData>) {
  const invalid = (data.issueCount ?? 0) > 0;
  const statusMeta = data.status ? nodeStatusMeta[data.status] : null;
  const hint = data.connectHint;

  return (
    <div
      className={`group relative w-[248px] rounded-md bg-surface text-left transition-shadow duration-100 ease-standard ${
        invalid
          ? "border-[1.5px] border-dashed border-status-failed-solid shadow-1"
          : selected
            ? "border-[1.5px] border-text shadow-2"
            : hint?.kind === "takes"
              ? "border-[1.5px] border-status-success-solid shadow-2"
              : "border border-border-strong shadow-1 hover:shadow-2"
      } ${hint?.kind === "nothing" ? "opacity-60" : ""}`}
    >
      {/* §15.2: handles are 10 px but need a 24 px hit area, so the visible circle sits in a larger target. */}
      {!data.readOnly && <Handle type="target" position={Position.Left} className={HANDLE} />}

      <div className="flex items-start gap-2.5 p-3">
        <AgentIcon agentType={data.agentType} icon={data.icon} family={data.family} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-body-md font-medium text-text" title={data.title}>
            {data.title}
          </p>
          {/* The step number only appears once connected — connecting is what orders the chain. */}
          <p className="text-overline uppercase text-text-muted">
            {data.agentType.replace(/_/g, " ")}
            {data.step ? ` · Step ${data.step}` : ""}
          </p>
        </div>
      </div>

      {hint ? (
        <p
          className={`flex items-center gap-1.5 border-t border-border px-3 py-2 text-body-sm ${
            hint.kind === "takes" ? "text-status-success-fg" : "text-text-muted"
          }`}
        >
          <ArrowRightToLine size={14} aria-hidden className="shrink-0" />
          {hint.kind === "takes" ? `Takes ${hint.items.join(" · ")}` : `Can't use anything from ${hint.from}`}
        </p>
      ) : data.problems.length > 0 ? (
        <ul className="grid list-none gap-0.5 border-t border-border px-3 py-2">
          {data.problems.slice(0, 2).map((problem) => (
            <li key={problem} className="flex items-start gap-1.5 text-body-sm text-status-failed-fg">
              <CircleAlert size={14} aria-hidden className="mt-0.5 shrink-0" />
              {problem}
            </li>
          ))}
        </ul>
      ) : data.summary.length > 0 ? (
        <p className="line-clamp-2 border-t border-border px-3 py-2 text-body-sm text-text-muted">
          {data.summary.join(" · ")}
        </p>
      ) : Object.keys(data.configuration).length === 0 ? (
        <p className="border-t border-border px-3 py-2 text-body-sm text-text-subtle">Default settings</p>
      ) : null}

      {(statusMeta || data.requiresApproval || invalid) && (
        <div className="flex items-center gap-2 border-t border-border px-3 py-2">
          {statusMeta && <StatusChip meta={statusMeta} />}
          {invalid && (
            <span className="text-body-sm text-status-failed-fg">
              {data.issueCount} {data.issueCount === 1 ? "issue" : "issues"}
            </span>
          )}
          <span className="flex-1" />
          {/* The gate mark: this step waits for a person before anything leaves the platform. */}
          {data.requiresApproval && (
            <span title="Waits for your approval" aria-label="Waits for your approval" className="font-mono text-mono-md text-status-approval-fg">
              ‖
            </span>
          )}
        </div>
      )}

      {!data.readOnly && <Handle type="source" position={Position.Right} className={HANDLE} />}
    </div>
  );
});
