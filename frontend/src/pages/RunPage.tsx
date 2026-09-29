import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
import { Button } from "@/design-system/components/Button";
import { Card } from "@/design-system/components/Card";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta, TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { endpoints } from "@/lib/api";

export function RunPage() {
  const { runId = "" } = useParams(); const client = useQueryClient();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => endpoints.runState(runId), refetchInterval: (q) => q.state.data && TERMINAL_RUN_STATUSES.has(q.state.data.status) ? false : 2000 });
  const outputs = useQuery({ queryKey: ["run-outputs", runId], queryFn: () => endpoints.runOutputs(runId), enabled: Boolean(runId) });
  const cancel = useMutation({ mutationFn: () => endpoints.cancel(runId), onSuccess: () => client.invalidateQueries({ queryKey: ["run", runId] }) });
  const state = run.data;
  return <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Run" }]}><PageBody width="narrow">
    {run.isError && <p role="alert" className="text-status-failed-fg">Couldn't load this run.</p>}
    {state && <div className="grid gap-5"><header className="flex flex-wrap items-center gap-3"><h1 className="text-heading-lg">Run</h1><StatusChip meta={runStatusMeta[state.status]} /><span className="font-mono text-mono-sm text-text-muted">{(state.nodes ?? []).filter((node) => node.status === "success").length} of {state.total_nodes} steps</span>{!TERMINAL_RUN_STATUSES.has(state.status) && <Button className="ml-auto" onClick={() => cancel.mutate()} loading={cancel.isPending}>Cancel run</Button>}</header>
      <ol className="grid gap-2">{(state.nodes ?? []).map((node, index) => <li key={node.node_id} className="rounded-md border border-border bg-surface p-4"><div className="flex items-center gap-3"><span>{index + 1}</span><span className="capitalize">{node.agent_type}</span><span className="text-text-muted">{node.status.replace("_", " ")}</span></div>{node.error_message && <pre className="mt-2 whitespace-pre-wrap text-status-failed-fg">{node.error_message}</pre>}</li>)}</ol>
      <section className="grid gap-3"><h2 className="text-heading-md">Outputs</h2>{outputs.data?.map((output) => <Card key={output.id} padding="compact" className="grid gap-2"><h3 className="capitalize">{output.agent_type}</h3><p className="text-text-muted">{output.filename ?? output.kind}</p></Card>)}</section>
      {TERMINAL_RUN_STATUSES.has(state.status) && <Link className="underline" to={`/runs/${runId}/outputs`}>See output details</Link>}
    </div>}
  </PageBody></AppShell>;
}
