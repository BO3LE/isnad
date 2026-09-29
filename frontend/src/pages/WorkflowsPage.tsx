import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell, PageBody, PageHeader } from "@/components/app/AppShell";
import { WorkflowCard } from "@/components/workflows/WorkflowCard";
import { WorkflowTable } from "@/components/workflows/WorkflowTable";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { Card } from "@/design-system/components/Card";
import { ConfirmDialog } from "@/design-system/components/Dialog";
import { EmptyState } from "@/design-system/components/EmptyState";
import { SearchInput } from "@/design-system/components/Input";
import type { MenuItem } from "@/design-system/components/Menu";
import { Segmented } from "@/design-system/components/Segmented";
import { Select } from "@/design-system/components/Select";
import { SkeletonCard } from "@/design-system/components/Skeleton";
import { useToast } from "@/design-system/components/toast-context";
import { duplicateWorkflow, endpoints, type WorkflowSummary } from "@/lib/api";

// P-03 · Workflows (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §21 S-02.
//
// The "Start from a template" row is not here. S-02 wants three template cards, but nothing in the
// API marks a workflow as a template — no is_template field, no templates endpoint — so a template
// cannot be told apart from a workflow the user made. Guessing by name would break the moment
// somebody renames one. TODO(Hasan, C2): mark templates in the API, then the row is ~20 lines here.

type SortKey = "updated" | "name" | "lastRun";
type View = "grid" | "table";

const SORTS: { value: SortKey; label: string }[] = [
  { value: "updated", label: "Last edited" },
  { value: "name", label: "Name" },
  { value: "lastRun", label: "Last run" },
];

const VIEW_STORAGE_KEY = "gp-workflows-view";

function readView(): View {
  try {
    return localStorage.getItem(VIEW_STORAGE_KEY) === "table" ? "table" : "grid";
  } catch {
    return "grid";
  }
}

function sortWorkflows(list: WorkflowSummary[], key: SortKey): WorkflowSummary[] {
  const time = (value?: string | null) => (value ? new Date(value).getTime() : 0);
  return [...list].sort((a, b) => {
    if (key === "name") return a.name.localeCompare(b.name);
    if (key === "lastRun") return time(b.last_run?.created_at) - time(a.last_run?.created_at);
    return time(b.updated_at) - time(a.updated_at);
  });
}

export function WorkflowsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("updated");
  const [view, setView] = useState<View>(readView);
  const [pendingDelete, setPendingDelete] = useState<WorkflowSummary | null>(null);

  const workflows = useQuery({ queryKey: ["workflows"], queryFn: endpoints.workflows });
  // AT-12: the chain's icons come from what each agent published, not from its name. Shared cache
  // with the canvas, so this costs nothing on a second visit.
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog, staleTime: 5 * 60_000 });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["workflows"] });

  const create = useMutation({
    mutationFn: () => endpoints.createWorkflow("Untitled workflow"),
    onSuccess: (workflow) => navigate(`/workflows/${workflow.id}`),
    onError: () => toast({ variant: "error", message: "Couldn't create the workflow. Check your connection." }),
  });

  const duplicate = useMutation({
    mutationFn: (id: string) => duplicateWorkflow(id),
    onSuccess: (copy) => {
      refresh();
      toast({ message: `Duplicated as “${copy.name}”.` });
    },
    onError: () => toast({ variant: "error", message: "Couldn't duplicate the workflow." }),
  });

  const remove = useMutation({
    // React Query passes (variables, context); wrap so only the id reaches the endpoint.
    mutationFn: (id: string) => endpoints.deleteWorkflow(id),
    onSuccess: (_result, id) => {
      refresh();
      const name = workflows.data?.find((w) => w.id === id)?.name;
      toast({ message: name ? `Deleted “${name}”.` : "Workflow deleted." });
    },
    onError: () => toast({ variant: "error", message: "Couldn't delete the workflow." }),
  });

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => endpoints.renameWorkflow(id, name),
    onSuccess: refresh,
    onError: () => toast({ variant: "error", message: "Couldn't rename the workflow." }),
  });

  // Memoised so the filter below is not recomputed on every render by a fresh [] identity.
  const all = useMemo(() => workflows.data ?? [], [workflows.data]);
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const matched = query ? all.filter((w) => w.name.toLowerCase().includes(query)) : all;
    return sortWorkflows(matched, sort);
  }, [all, search, sort]);

  function setViewPersisted(next: View) {
    setView(next);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      // A remembered view is a convenience; losing it is not worth surfacing.
    }
  }

  function actionsFor(workflow: WorkflowSummary): MenuItem[] {
    return [
      { id: "open", label: "Open", onSelect: () => navigate(`/workflows/${workflow.id}`) },
      {
        id: "rename",
        label: "Rename",
        onSelect: () => {
          const next = window.prompt("Workflow name", workflow.name)?.trim();
          if (next && next !== workflow.name) rename.mutate({ id: workflow.id, name: next });
        },
      },
      { id: "duplicate", label: "Duplicate", onSelect: () => duplicate.mutate(workflow.id) },
      { id: "delete", label: "Delete", danger: true, separated: true, onSelect: () => setPendingDelete(workflow) },
    ];
  }

  return (
    <AppShell crumbs={[{ label: "Workflows" }]}>
      <PageBody>
        <PageHeader
          title="Workflows"
          description="Each workflow is a chain of agents. Open one to edit or run it."
          actions={
            <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => create.mutate()} loading={create.isPending}>
              New workflow
            </Button>
          }
        />

        {workflows.isError && (
          <Banner variant="error" action={<Button size="sm" onClick={() => workflows.refetch()}>Retry</Button>}>
            Couldn't load your workflows. {workflows.error.message}
          </Banner>
        )}

        {/* The toolbar is pointless with nothing to filter, and it crowds the first-run empty state. */}
        {all.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-[220px] flex-1">
              <SearchInput label="Search workflows" value={search} onValueChange={setSearch} placeholder="Search workflows" />
            </div>
            <label className="flex items-center gap-2 text-body-sm text-text-muted">
              Sort
              <Select
                aria-label="Sort workflows"
                value={sort}
                onChange={(event) => setSort(event.target.value as SortKey)}
                options={SORTS}
                className="w-[150px]"
              />
            </label>
            <Segmented
              label="View"
              value={view}
              onChange={setViewPersisted}
              options={[
                { value: "grid", label: "Grid" },
                { value: "table", label: "Table" },
              ]}
            />
          </div>
        )}

        {workflows.isPending && (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, index) => (
              <SkeletonCard key={index} />
            ))}
          </div>
        )}

        {/* First visit — §18.2. */}
        {!workflows.isPending && all.length === 0 && !workflows.isError && (
          <Card padding="compact">
            <EmptyState
              title="Build your first chain"
              body="A workflow is a line of agents: research a topic, write it up, turn it into a video, then publish it. Start with one agent and add more as you go."
              actions={
                <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => create.mutate()} loading={create.isPending}>
                  New workflow
                </Button>
              }
            />
          </Card>
        )}

        {/* Searched, found nothing — a different state with a different way out. */}
        {all.length > 0 && visible.length === 0 && (
          <Card padding="compact">
            <EmptyState
              art={false}
              title={`No workflows match “${search.trim()}”.`}
              actions={<Button onClick={() => setSearch("")}>Clear search</Button>}
            />
          </Card>
        )}

        {visible.length > 0 &&
          (view === "grid" ? (
            <ul className="grid list-none gap-6 p-0 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((workflow) => (
                <li key={workflow.id}>
                  <WorkflowCard workflow={workflow} agents={catalog.data} actions={actionsFor(workflow)} />
                </li>
              ))}
            </ul>
          ) : (
            <WorkflowTable workflows={visible} agents={catalog.data} actionsFor={actionsFor} />
          ))}
      </PageBody>

      <ConfirmDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
          setPendingDelete(null);
        }}
        loading={remove.isPending}
        title={`Delete “${pendingDelete?.name ?? ""}”?`}
        description="Its runs and their files will be deleted. This can't be undone."
        confirmLabel="Delete workflow"
      />
    </AppShell>
  );
}
