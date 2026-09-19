import { Ellipsis } from "lucide-react";
import { Link } from "react-router-dom";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { Skeleton } from "@/design-system/components/Skeleton";
import { IconButton } from "@/design-system/components/IconButton";
import { Menu, type MenuItem } from "@/design-system/components/Menu";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta } from "@/design-system/status/statusMeta";
import { formatRelativeTime, pluralise } from "@/lib/format";
import { manifestFor } from "@/design-system/agents/agentMeta";
import type { AgentManifest, WorkflowSummary } from "@/lib/api";

// DESIGN-SYSTEM.md §14.8 workflow card + §21 S-02.
const MAX_ICONS = 6;

export function WorkflowCard({
  workflow,
  agents,
  actions,
}: {
  workflow: WorkflowSummary;
  agents?: AgentManifest[];
  actions: MenuItem[];
}) {
  const steps = workflow.agent_types?.length ?? 0;
  const shown = (workflow.agent_types ?? []).slice(0, MAX_ICONS);
  const overflow = steps - shown.length;
  const lastRun = workflow.last_run;
  const awaitingApproval = lastRun?.status === "awaiting_approval";

  return (
    // §14.8: the whole card is the link target, and the More menu sits outside it so there is no
    // nested interactive element. Hence the wrapper rather than putting the menu inside the Link.
    <div className="group relative grid gap-3 rounded-md border border-border bg-surface p-6 shadow-1 transition-shadow duration-100 ease-standard focus-within:shadow-2 hover:shadow-2">
      <div className="flex items-start justify-between gap-2">
        <Link
          to={`/workflows/${workflow.id}`}
          className="text-heading-sm text-text after:absolute after:inset-0 after:content-[''] hover:no-underline"
        >
          {workflow.name}
        </Link>
        <Menu
          className="relative z-shell -mr-1 -mt-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100"
          items={actions}
          trigger={(props) => (
            <IconButton {...props} size="sm" label={`Actions for ${workflow.name}`} icon={<Ellipsis size={16} aria-hidden />} />
          )}
        />
      </div>

      {steps > 0 ? (
        <div className="flex items-center gap-1.5">
          {agents
              ? shown.map((type, index) => (
                  <AgentIcon key={`${type}-${index}`} {...manifestFor(type, agents)} size="sm" />
                ))
              : shown.map((_type, index) => <Skeleton key={index} className="h-6 w-6 rounded-xs" />)}
          {overflow > 0 && <span className="text-caption text-text-muted">+{overflow}</span>}
        </div>
      ) : (
        <span className="text-body-sm text-text-subtle">No steps yet</span>
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-body-sm text-text-muted">
        {lastRun ? (
          <>
            <StatusChip meta={runStatusMeta[lastRun.status]} />
            <span>{formatRelativeTime(lastRun.completed_at ?? lastRun.created_at)}</span>
          </>
        ) : (
          <span>Never run</span>
        )}
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <span>{pluralise(steps, "step")}</span>
      </div>

      {awaitingApproval && (
        <Link
          to={`/runs/${lastRun.id}`}
          className="relative z-shell justify-self-start text-body-md font-medium text-status-approval-fg hover:underline"
        >
          Review
        </Link>
      )}

    </div>
  );
}
