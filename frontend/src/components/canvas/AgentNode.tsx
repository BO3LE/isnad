import { Ellipsis } from "lucide-react";
import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { IconButton } from "@/design-system/components/IconButton";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta } from "@/design-system/status/statusMeta";
import type { NodeStatus } from "@/lib/api";

// DESIGN-SYSTEM.md §15.2 — "the most important component in the product".
export interface AgentNodeData {
  agentType: string;
  title: string;
  icon?: string | null;
  family?: string | null;
  summary: string;
  step?: number;
  requiresApproval: boolean;
  /** Set once /validate has run; a dashed red border and a count badge (§15.2 invalid state). */
  issueCount?: number;
  /** Live status during a run; absent in edit mode, where no chip is shown. */
  status?: NodeStatus;
  readOnly?: boolean;
  onOpenMenu?: (nodeId: string) => void;
}

const HANDLE = "!h-2.5 !w-2.5 !border-[1.5px] !border-border-strong !bg-surface";

export const AgentNode = memo(function AgentNode({ id, data, selected }: NodeProps<AgentNodeData>) {
  const invalid = (data.issueCount ?? 0) > 0;
  const statusMeta = data.status ? nodeStatusMeta[data.status] : null;

  return (
    <div
      className={`group relative w-[248px] min-h-[96px] rounded-md bg-surface transition-shadow duration-100 ease-standard ${
        invalid
          ? "border-[1.5px] border-dashed border-status-failed-solid shadow-1"
          : selected
            ? "border-[1.5px] border-text shadow-2"
            : "border border-border-strong shadow-1 hover:shadow-2"
      }`}
    >
      {/* §15.2: handles are 10 px but need a 24 px hit area, so the visible circle sits in a larger target. */}
      {!data.readOnly && <Handle type="target" position={Position.Left} className={HANDLE} />}

      <div className="flex items-start gap-2 p-3">
        <AgentIcon agentType={data.agentType} icon={data.icon} family={data.family} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-body-md font-medium text-text" title={data.title}>
            {data.title}
          </p>
          <p className="text-overline uppercase text-text-muted">
            {data.agentType}
            {data.step ? ` · Step ${data.step}` : ""}
          </p>
        </div>
        {data.onOpenMenu && (
          <IconButton
            size="sm"
            label={`Actions for ${data.title}`}
            icon={<Ellipsis size={16} aria-hidden />}
            onClick={(event) => {
              event.stopPropagation();
              data.onOpenMenu?.(id);
            }}
            className={`nodrag opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100 ${selected ? "opacity-100" : ""}`}
          />
        )}
      </div>

      {data.summary && (
        <p className="line-clamp-2 border-t border-border px-3 py-2 text-body-sm text-text-muted">{data.summary}</p>
      )}

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
            <span title="Requires approval" aria-label="Requires approval" className="font-mono text-mono-sm text-status-approval-fg">
              ‖
            </span>
          )}
        </div>
      )}

      {!data.readOnly && <Handle type="source" position={Position.Right} className={HANDLE} />}
    </div>
  );
});
