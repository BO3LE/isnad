import { Ellipsis } from "lucide-react";
import { Link } from "react-router-dom";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { IconButton } from "@/design-system/components/IconButton";
import { Menu, type MenuItem } from "@/design-system/components/Menu";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta } from "@/design-system/status/statusMeta";
import { formatAbsoluteTime, formatRelativeTime } from "@/lib/format";
import { manifestFor } from "@/design-system/agents/agentMeta";
import type { AgentManifest, WorkflowSummary } from "@/lib/api";

// DESIGN-SYSTEM.md §14.16 data table + §21 S-02 table view: name · steps · last run · last edited.
export function WorkflowTable({
  workflows,
  agents,
  actionsFor,
}: {
  workflows: WorkflowSummary[];
  agents?: AgentManifest[];
  actionsFor: (workflow: WorkflowSummary) => MenuItem[];
}) {
  return (
    // §14.16: horizontal scroll lives inside the table container, never on the page.
    <div className="overflow-x-auto rounded-md border border-border bg-surface">
      <table className="w-full border-collapse text-body-md">
        <thead>
          <tr className="bg-bg-sunken text-left">
            <th scope="col" className="px-3 py-2.5 text-body-sm font-semibold text-text">
              Name
            </th>
            <th scope="col" className="px-3 py-2.5 text-body-sm font-semibold text-text">
              Steps
            </th>
            <th scope="col" className="px-3 py-2.5 text-body-sm font-semibold text-text">
              Last run
            </th>
            <th scope="col" className="px-3 py-2.5 text-body-sm font-semibold text-text">
              Last edited
            </th>
            <th scope="col" className="w-12 px-3 py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {workflows.map((workflow) => {
            const steps = workflow.agent_types ?? [];
            const lastRun = workflow.last_run;
            return (
              <tr key={workflow.id} className="border-t border-border transition-colors hover:bg-surface-hover">
                <td className="px-3 py-2.5">
                  <Link to={`/workflows/${workflow.id}`} className="font-medium text-text hover:underline">
                    {workflow.name}
                  </Link>
                </td>
                <td className="px-3 py-2.5">
                  <span className="flex items-center gap-1">
                    {steps.slice(0, 6).map((type, index) => (
                      <AgentIcon key={`${type}-${index}`} {...manifestFor(type, agents)} size="sm" />
                    ))}
                    {steps.length > 6 && <span className="text-caption text-text-muted">+{steps.length - 6}</span>}
                    {steps.length === 0 && <span className="text-body-sm text-text-subtle">—</span>}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  {lastRun ? (
                    <span className="flex items-center gap-2">
                      <StatusChip meta={runStatusMeta[lastRun.status]} />
                      <span className="text-body-sm text-text-muted">
                        {formatRelativeTime(lastRun.completed_at ?? lastRun.created_at)}
                      </span>
                    </span>
                  ) : (
                    <span className="text-body-sm text-text-muted">Never run</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-body-sm text-text-muted" title={formatAbsoluteTime(workflow.updated_at)}>
                  {formatRelativeTime(workflow.updated_at)}
                </td>
                <td className="px-3 py-2.5">
                  <Menu
                    items={actionsFor(workflow)}
                    trigger={(props) => (
                      <IconButton {...props} size="sm" label={`Actions for ${workflow.name}`} icon={<Ellipsis size={16} aria-hidden />} />
                    )}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
