import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Copy, Download } from "lucide-react";
import { Fragment, useCallback, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
import { RunTabs } from "@/components/runs/RunTabs";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { agentTitle, manifestFor } from "@/design-system/agents/agentMeta";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { EmptyState } from "@/design-system/components/EmptyState";
import { SearchInput } from "@/design-system/components/Input";
import { Segmented } from "@/design-system/components/Segmented";
import { Select } from "@/design-system/components/Select";
import { Skeleton } from "@/design-system/components/Skeleton";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta, rejectedMeta, runStatusMeta, TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { useToast } from "@/design-system/components/toast-context";
import { ApiError, endpoints, type AgentManifest, type LogEntry, type NodeStatus } from "@/lib/api";
import { formatDuration, formatTimeOfDay, type TimeZonePreference } from "@/lib/format";
import { applyFilter, attemptsOf, isFiltered, lastAttemptText, MAX_RETRIES, NO_FILTER, retryLabel, retryWaitLabel, toCsv, type LogFilter } from "@/lib/logs";
import { stepError } from "@/lib/runPlayback";
import { NotFoundState } from "@/pages/NotFoundPage";

// P-08 (DESIGN-SYSTEM §21 S-07) — exactly what happened in a run, and a file you can hand to
// someone else. This is the page that has to answer "why did it stop?" without anyone reading a
// server log.
//
// Nothing here names an agent: a row's title and glyph come from the catalog (AT-12).

const POLL_MS = 2000;

/** Statuses offered in the filter, in the order a run moves through them. */
const STATUS_ORDER: NodeStatus[] = ["pending", "running", "retrying", "awaiting_approval", "success", "failed", "skipped"];

function readFilter(params: URLSearchParams): LogFilter {
  return {
    text: params.get("q") ?? "",
    statuses: (params.getAll("status") as NodeStatus[]).filter((s) => STATUS_ORDER.includes(s)),
    agents: params.getAll("agent"),
  };
}

/** The filter as query parameters — §21 S-07 asks for filters to be reflected in the URL. */
function writeFilter(filter: LogFilter, zone: TimeZonePreference): URLSearchParams {
  const params = new URLSearchParams();
  if (filter.text.trim()) params.set("q", filter.text.trim());
  for (const status of filter.statuses) params.append("status", status);
  for (const agent of filter.agents) params.append("agent", agent);
  if (zone === "utc") params.set("tz", "utc");
  return params;
}

/** What the Error column says — and what its tooltip says, which must be the same sentence. */
function errorCell(row: LogEntry): string {
  return stepError(row.error_message)?.rejected ? "You stopped this step." : lastAttemptText(row.error_message);
}

function Duration({ ms }: { ms: number | null | undefined }) {
  if (ms == null) return <span className="text-text-subtle">—</span>;
  return <span className="font-mono text-mono-sm text-text-muted">{formatDuration(ms / 1000)}</span>;
}

/** The retries cell: a plain count, or §16.5's "Retrying n/3" while the step is between attempts. */
function Retries({ row }: { row: LogEntry }) {
  if (row.status === "retrying") {
    return <span className="whitespace-nowrap text-body-sm text-status-retrying-fg">{retryLabel(row.retry_count)}</span>;
  }
  // A step spends most of a retry cycle `running`, not `retrying` — the orchestrator raises
  // `retry_count`, writes `retrying`, waits, then writes `running` with the same count. Showing a
  // bare "1" there says it retried once and hides that a second attempt is in flight right now.
  if (row.status === "running" && row.retry_count >= 1) {
    return <span className="whitespace-nowrap text-body-sm text-status-running-fg">Attempt {row.retry_count + 1}</span>;
  }
  // N9 / §21 S-07: a step that never started has no attempts to count, so it reads "—" like its
  // neighbouring columns. A step that ran and needed no retry really did retry zero times.
  if (row.started_at == null) return <span className="text-text-subtle">—</span>;
  if (row.retry_count < 1) return <span className="text-text-subtle">0</span>;
  return <span className="font-mono text-mono-sm text-text">{row.retry_count}</span>;
}

/**
 * The attempt timeline (§21 S-07's expanded row).
 *
 * Every attempt's message is real — the worker appends each failure behind an `[attempt N]` marker
 * — but per-attempt timestamps and durations are not recorded anywhere, so this narrates the wait
 * the orchestrator took rather than inventing clock times it does not have.
 */
function Attempts({ row }: { row: LogEntry }) {
  const attempts = attemptsOf(row.error_message);
  if (attempts.length === 0) return null;

  return (
    <ol className="grid gap-1.5">
      {attempts.map((attempt, index) => {
        // Both numbers come from the marker the worker wrote, never from the array position: two
        // numbers printed side by side must not be able to drift apart.
        const isLast = index === attempts.length - 1;
        const wait = isLast && row.status !== "retrying" ? null : retryWaitLabel(attempt.number);
        return (
          <li key={attempt.number} className="grid gap-0.5 border-l-2 border-border pl-3 text-body-sm">
            <p className="text-text">
              <span className="font-medium">Attempt {attempt.number}</span>
              <span className="text-text-muted"> · {attempt.text}</span>
            </p>
            {wait !== null && <p className="text-caption text-text-muted">{wait}</p>}
          </li>
        );
      })}
      {row.status === "failed" && row.retry_count >= MAX_RETRIES && (
        <li className="pl-3 text-body-sm text-status-failed-fg">
          Out of attempts — the run stopped here and the steps after it were skipped.
        </li>
      )}
    </ol>
  );
}

function Expanded({ row, zone, onCopy }: { row: LogEntry; zone: TimeZonePreference; onCopy: (value: string) => void }) {
  const error = stepError(row.error_message);

  return (
    <div className="grid gap-3 border-t border-border bg-bg-sunken px-4 py-3">
      {error?.rejected ? (
        <p className="text-body-sm text-text-muted">You rejected this step, so nothing was sent.</p>
      ) : (
        <Attempts row={row} />
      )}

      <dl className="grid gap-x-4 gap-y-1 text-body-sm sm:grid-cols-[auto_1fr]">
        {row.started_at && (
          <>
            <dt className="text-text-muted">Started</dt>
            <dd className="font-mono text-mono-sm text-text">{formatTimeOfDay(row.started_at, zone)}</dd>
          </>
        )}
        {row.completed_at && (
          <>
            <dt className="text-text-muted">Finished</dt>
            <dd className="font-mono text-mono-sm text-text">{formatTimeOfDay(row.completed_at, zone)}</dd>
          </>
        )}
        <dt className="text-text-muted">Step id</dt>
        <dd className="flex items-center gap-2">
          <span className="truncate font-mono text-mono-sm text-text">{row.node_id}</span>
          <button
            type="button"
            onClick={() => onCopy(row.node_id)}
            className="flex shrink-0 items-center gap-1 rounded-xs text-caption text-text-muted hover:text-text"
          >
            <Copy size={12} aria-hidden /> Copy
            <span className="sr-only"> step id</span>
          </button>
        </dd>
      </dl>
    </div>
  );
}

export function LogsPage() {
  const { runId = "" } = useParams();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState<string | null>(null);

  const filter = useMemo(() => readFilter(params), [params]);
  const zone: TimeZonePreference = params.get("tz") === "utc" ? "utc" : "local";

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => endpoints.runState(runId),
    enabled: Boolean(runId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
    // The run has to be re-read, not just the log: the chip above the table is the run's status,
    // and `active` below is derived from it. Without this the run is fetched once, the chip is
    // frozen on whatever it said when the page opened, and — because `active` can then never turn
    // false — the log below polls a finished run for as long as the tab stays open.
    refetchInterval: (query) => (query.state.data && TERMINAL_RUN_STATUSES.has(query.state.data.status) ? false : POLL_MS),
    refetchIntervalInBackground: true,
  });

  const active = run.data !== undefined && !TERMINAL_RUN_STATUSES.has(run.data.status);

  const logs = useQuery({
    queryKey: ["run-logs", runId],
    queryFn: () => endpoints.runLogs(runId),
    enabled: Boolean(runId),
    // §21 S-07: rows update in place while the run is going. A finished run never changes again.
    refetchInterval: active ? POLL_MS : false,
  });

  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog, staleTime: 5 * 60_000 });
  const agents: AgentManifest[] | undefined = catalog.data;

  const titleOf = useCallback((agentType: string) => agentTitle(agentType, agents), [agents]);

  const rows = useMemo(() => logs.data ?? [], [logs.data]);
  const shown = useMemo(() => applyFilter(rows, filter, titleOf), [rows, filter, titleOf]);

  // The step number is the row's place in the run, which is the order the API returns them in
  // (api/routers/runs.py orders by position_order). Filtering must not renumber the steps.
  const numberOf = useMemo(() => new Map(rows.map((row, index) => [row.node_id, index + 1])), [rows]);

  // A run the person stopped is not a failure (§2 rule 7). The run itself only reports "failed",
  // so the reason comes from the step that carries the rejection.
  const rejected = run.data?.status === "failed" && rows.some((row) => stepError(row.error_message)?.rejected === true);

  const update = (next: LogFilter, nextZone: TimeZonePreference = zone) => setParams(writeFilter(next, nextZone), { replace: true });

  const agentOptions = useMemo(() => {
    const seen = [...new Set(rows.map((row) => row.agent_type))];
    return [{ value: "", label: "All agents" }, ...seen.map((type) => ({ value: type, label: titleOf(type) }))];
  }, [rows, titleOf]);

  const exportCsv = () => {
    // Exactly the rows on screen (§21 S-07), so the file matches what was being looked at.
    const blob = new Blob([toCsv(shown)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `run-${runId}-logs.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    // Freed on the next turn of the loop: revoking synchronously can cancel the download in Safari.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const copyId = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast({ variant: "success", message: "Copied." });
    } catch {
      toast({ variant: "error", message: "Couldn't copy — your browser blocked it." });
    }
  };

  if (run.isError && run.error instanceof ApiError && run.error.status === 404) {
    return <NotFoundState message="We couldn't find that run." />;
  }

  return (
    <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Run", to: `/runs/${runId}` }, { label: "Logs" }]}>
      <PageBody>
        <header className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-heading-lg text-text">Logs</h1>
            {run.data && <StatusChip meta={rejected ? rejectedMeta : runStatusMeta[run.data.status]} />}
            <Button
              className="ml-auto"
              variant="secondary"
              onClick={exportCsv}
              disabled={shown.length === 0}
              icon={<Download size={16} aria-hidden />}
            >
              Export CSV
            </Button>
          </div>
          <RunTabs runId={runId} current="logs" />
        </header>

        {run.isError && <Banner variant="error">Couldn&apos;t load this run.</Banner>}
        {logs.isError && (
          <Banner variant="error" action={<Button variant="ghost" onClick={() => logs.refetch()}>Try again</Button>}>
            Couldn&apos;t load this run&apos;s log.
          </Banner>
        )}

        {rows.length > 0 && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid min-w-[12rem] flex-1 gap-1.5 text-body-sm text-text-muted" htmlFor="log-search">
              Search
              <SearchInput
                id="log-search"
                label="Search the log by agent or error text"
                value={filter.text}
                onValueChange={(text) => update({ ...filter, text })}
                placeholder="Agent or error text"
              />
            </label>
            <label className="grid gap-1.5 text-body-sm text-text-muted">
              Status
              <Select
                className="w-44"
                value={filter.statuses[0] ?? ""}
                onChange={(event) => update({ ...filter, statuses: event.target.value ? [event.target.value as NodeStatus] : [] })}
                options={[
                  { value: "", label: "All statuses" },
                  ...STATUS_ORDER.map((status) => ({ value: status, label: nodeStatusMeta[status].label })),
                ]}
              />
            </label>
            <label className="grid gap-1.5 text-body-sm text-text-muted">
              Agent
              <Select
                className="w-44"
                value={filter.agents[0] ?? ""}
                onChange={(event) => update({ ...filter, agents: event.target.value ? [event.target.value] : [] })}
                options={agentOptions}
              />
            </label>
            <div className="grid gap-1.5 text-body-sm text-text-muted">
              <span aria-hidden>Times</span>
              <Segmented
                label="Times — show the clock in local time or UTC"
                value={zone}
                onChange={(next) => update(filter, next as TimeZonePreference)}
                options={[
                  { value: "local", label: "Local" },
                  { value: "utc", label: "UTC" },
                ]}
              />
            </div>
          </div>
        )}

        {logs.isPending && (
          <div className="grid gap-2" aria-busy>
            {[0, 1, 2, 3, 4].map((n) => (
              <Skeleton key={n} className="h-12 w-full" />
            ))}
          </div>
        )}

        {!logs.isPending && rows.length === 0 && !logs.isError && (
          <EmptyState title="Nothing logged yet" body="Logs appear as soon as the first step starts." />
        )}

        {rows.length > 0 && shown.length === 0 && (
          <EmptyState
            art={false}
            title="No steps match"
            body="Nothing in this run matches the filter."
            actions={<Button variant="secondary" onClick={() => update(NO_FILTER)}>Clear the filter</Button>}
          />
        )}

        {shown.length > 0 && (
          <>
            {/* Below `md` the table becomes a list of cards (§21 S-07, §22): seven columns cannot
                be read on a phone, and a horizontally scrolling table is worse than a stack. */}
            <ul className="grid gap-2 md:hidden">
              {shown.map((row) => (
                <LogCard
                  key={row.node_id}
                  row={row}
                  step={numberOf.get(row.node_id) ?? 0}
                  agents={agents}
                  zone={zone}
                  expanded={open === row.node_id}
                  onToggle={() => setOpen(open === row.node_id ? null : row.node_id)}
                  onCopy={copyId}
                />
              ))}
            </ul>

            <div className="hidden rounded-md border border-border md:block">
              <table className="w-full border-collapse text-body-sm">
                <caption className="sr-only">
                  Every step in this run, with its status, timings, retries and error.
                </caption>
                {/* Sticky against the page scroll (§21 S-07): a long run runs the column names off
                    the top of the screen, and a log is unreadable without them. This is why the
                    wrapper above cannot clip its overflow — that would capture the sticky. */}
                <thead className="sticky top-0">
                  <tr className="border-b border-border bg-bg-sunken text-left text-text-muted [&>th:first-child]:rounded-tl-md [&>th:last-child]:rounded-tr-md">
                    <th scope="col" className="w-10 px-2 py-2">
                      <span className="sr-only">Expand</span>
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">Step</th>
                    <th scope="col" className="px-3 py-2 font-medium">Status</th>
                    <th scope="col" className="px-3 py-2 font-medium">Started</th>
                    <th scope="col" className="hidden px-3 py-2 font-medium xl:table-cell">Completed</th>
                    <th scope="col" className="px-3 py-2 font-medium">Duration</th>
                    <th scope="col" className="px-3 py-2 font-medium">Retries</th>
                    <th scope="col" className="px-3 py-2 font-medium">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((row) => {
                    const expanded = open === row.node_id;
                    const error = stepError(row.error_message);
                    const manifest = manifestFor(row.agent_type, agents);
                    const title = titleOf(row.agent_type);
                    const step = numberOf.get(row.node_id) ?? 0;

                    return (
                      // The key belongs on the fragment: a row and its detail are two <tr>s, and
                      // React keys the outermost element the map returns.
                      <Fragment key={row.node_id}>
                        <tr className="border-b border-border last:border-0 hover:bg-surface-hover">
                          <td className="px-2 py-2">
                            <button
                              type="button"
                              aria-expanded={expanded}
                              aria-controls={`log-detail-${row.node_id}`}
                              onClick={() => setOpen(expanded ? null : row.node_id)}
                              className="flex h-7 w-7 items-center justify-center rounded-xs text-text-muted hover:bg-surface-hover hover:text-text"
                            >
                              <ChevronRight
                                size={14}
                                aria-hidden
                                className={`transition-transform ${expanded ? "rotate-90" : ""}`}
                              />
                              <span className="sr-only">{expanded ? `Hide details for ${title}` : `Show details for ${title}`}</span>
                            </button>
                          </td>
                          <th scope="row" className="px-3 py-2 text-left font-normal">
                            <span className="flex items-center gap-2">
                              <span className="font-mono text-mono-sm text-text-muted">{step}</span>
                              {agents ? <AgentIcon icon={manifest?.icon} family={manifest?.family} size="sm" /> : <Skeleton className="h-6 w-6 rounded-xs" />}
                              <span className="text-text">{agents ? title : <Skeleton className="inline-block h-4 w-16 align-middle" />}</span>
                            </span>
                          </th>
                          <td className="px-3 py-2">
                            <StatusChip meta={error?.rejected ? rejectedMeta : nodeStatusMeta[row.status]} />
                          </td>
                          <td className="px-3 py-2 font-mono text-mono-sm text-text-muted">
                            {row.started_at ? formatTimeOfDay(row.started_at, zone) : <span className="text-text-subtle">—</span>}
                          </td>
                          <td className="hidden px-3 py-2 font-mono text-mono-sm text-text-muted xl:table-cell">
                            {row.completed_at ? formatTimeOfDay(row.completed_at, zone) : <span className="text-text-subtle">—</span>}
                          </td>
                          <td className="px-3 py-2">
                            <Duration ms={row.duration_ms} />
                          </td>
                          <td className="px-3 py-2">
                            <Retries row={row} />
                          </td>
                          {/* One string for the cell and its hover: they disagreed on a rejected
                              step, where the cell said "You stopped this step." and the tooltip
                              still showed the worker's "Rejected by reviewer." */}
                          <td className="max-w-[20rem] truncate px-3 py-2 text-text-muted" title={errorCell(row) || undefined}>
                            {errorCell(row) || <span className="text-text-subtle">—</span>}
                          </td>
                        </tr>
                        {expanded && (
                          <tr id={`log-detail-${row.node_id}`}>
                            <td colSpan={8} className="p-0">
                              <Expanded row={row} zone={zone} onCopy={copyId} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <p className="text-caption text-text-muted">
              {isFiltered(filter)
                ? `Export CSV writes these ${shown.length} of ${rows.length} steps, with timestamps in UTC.`
                : "Export CSV writes every step above, with timestamps in UTC."}
            </p>
          </>
        )}
      </PageBody>
    </AppShell>
  );
}

function LogCard({
  row,
  step,
  agents,
  zone,
  expanded,
  onToggle,
  onCopy,
}: {
  row: LogEntry;
  step: number;
  agents: AgentManifest[] | undefined;
  zone: TimeZonePreference;
  expanded: boolean;
  onToggle: () => void;
  onCopy: (value: string) => void;
}) {
  const manifest = manifestFor(row.agent_type, agents);
  const title = agentTitle(row.agent_type, agents);
  const error = stepError(row.error_message);

  return (
    <li className="rounded-md border border-border bg-surface shadow-1">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={`log-card-${row.node_id}`}
        onClick={onToggle}
        className="grid w-full gap-2 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="font-mono text-mono-sm text-text-muted">{step}</span>
          <AgentIcon icon={manifest?.icon} family={manifest?.family} size="sm" />
          <span className="text-body-md font-medium text-text">{title}</span>
          <span className="ml-auto">
            <StatusChip meta={error?.rejected ? rejectedMeta : nodeStatusMeta[row.status]} />
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-3 text-body-sm text-text-muted">
          {row.started_at && <span className="font-mono text-mono-sm">{formatTimeOfDay(row.started_at, zone)}</span>}
          <Duration ms={row.duration_ms} />
          <Retries row={row} />
        </span>
      </button>
      {expanded && (
        <div id={`log-card-${row.node_id}`}>
          <Expanded row={row} zone={zone} onCopy={onCopy} />
        </div>
      )}
    </li>
  );
}
