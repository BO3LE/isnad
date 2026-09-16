import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
import { Button } from "@/design-system/components/Button";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta } from "@/design-system/status/statusMeta";
import { endpoints } from "@/lib/api";

// S-02 skeleton (DESIGN-SYSTEM.md §21). TODO(W2, Ahmed): cards per §14.8, templates row, empty state art.
export function WorkflowsPage() {
  const navigate = useNavigate();
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: endpoints.workflows });
  const create = useMutation({
    mutationFn: () => endpoints.createWorkflow("Untitled workflow"),
    onSuccess: (wf) => navigate(`/workflows/${wf.id}`),
  });

  return (
    <AppShell crumbs={[{ label: "Workflows" }]}>
      <PageBody>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="grid gap-1">
            <h1 className="text-heading-xl">Workflows</h1>
            <p className="text-text-muted">Each workflow is a chain of agents. Open one to edit or run it.</p>
          </div>
          <Button variant="primary" onClick={() => create.mutate()} loading={create.isPending}>
            <Plus size={16} aria-hidden /> New workflow
          </Button>
        </div>

        {workflows.isPending && <p className="text-text-muted">Loading workflows…</p>}
        {workflows.isError && (
          <p role="alert" className="text-status-failed-fg">
            {workflows.error.message}
          </p>
        )}
        {workflows.data?.length === 0 && <p className="text-text-muted">No workflows yet. Create your first chain.</p>}

        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {workflows.data?.map((wf) => (
            <li key={wf.id}>
              <Link
                to={`/workflows/${wf.id}`}
                className="grid gap-3 rounded-md border border-border bg-surface p-5 shadow-1 transition-shadow hover:shadow-2 hover:no-underline"
              >
                <span className="text-heading-sm text-text">{wf.name}</span>
                <span className="font-mono text-mono-sm text-text-muted">{wf.agent_types.join(" → ") || "empty"}</span>
                <span className="flex items-center gap-2 text-body-sm text-text-muted">
                  {wf.last_run ? <StatusChip meta={runStatusMeta[wf.last_run.status]} /> : "Never run"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </PageBody>
    </AppShell>
  );
}
