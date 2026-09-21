import { useMutation, useQuery } from "@tanstack/react-query";
import { Copy, Download, ExternalLink, FileText, Sparkles } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppShell, PageBody } from "@/components/app/AppShell";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { Card } from "@/design-system/components/Card";
import { EmptyState } from "@/design-system/components/EmptyState";
import { Skeleton } from "@/design-system/components/Skeleton";
import { StatusChip } from "@/design-system/status/StatusChip";
import { rejectedMeta, runStatusMeta, TERMINAL_RUN_STATUSES } from "@/design-system/status/statusMeta";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { formatBytes, formatDuration, pluralise } from "@/lib/format";
import { ApiError, endpoints, type AgentManifest, type RunOutput, type RunState } from "@/lib/api";
import { stepError } from "@/lib/runPlayback";
import { validationFrom } from "@/lib/validation";
import { useToast } from "@/design-system/components/toast-context";
import { NotFoundState } from "@/pages/NotFoundPage";

// P-09 (DESIGN-SYSTEM §21 S-08) — everything a run produced: what went out, the files themselves,
// and the words. A run is only worth anything if the person can get at what it made.
//
// Nothing here knows an agent: a card's shape comes from the output's kind and media type, and its
// heading from the catalog (AT-12).

const POLL_MS = 2000;

const isImage = (o: RunOutput) => (o.mime_type ?? "").startsWith("image/");
const isVideo = (o: RunOutput) => (o.mime_type ?? "").startsWith("video/");

/** The file's type in the words a person uses, from the name rather than the media type. */
function kindLabel(output: RunOutput): string {
  // The suffix is what the person sees and what lands on disk; the media type is often useless
  // ("application/octet-stream"). Only a short, alphanumeric tail counts as a suffix, so
  // "report.2026-09-20" is not labelled "2026-09-20".
  const suffix = output.filename?.split(".").pop() ?? "";
  if (suffix && suffix !== output.filename && /^[a-z0-9]{1,5}$/i.test(suffix)) return suffix.toUpperCase();
  return ((output.mime_type ?? "file").split("/").pop() ?? "file").slice(0, 12).toUpperCase();
}

async function copy(value: string, done: string, toast: ReturnType<typeof useToast>) {
  try {
    await navigator.clipboard.writeText(value);
    toast({ variant: "success", message: done });
  } catch {
    // Denied, or an insecure context. Saying nothing at all is the one thing we must not do.
    toast({ variant: "error", message: "Couldn't copy — your browser blocked it." });
  }
}

function useLink(id: string) {
  // The file never changes, but the URL can: production mints a signed one that expires, and
  // `expires_in` says when. Holding it forever would leave a dead Download on a page left open.
  return useQuery({
    queryKey: ["output", id],
    queryFn: () => endpoints.output(id),
    staleTime: (query) => {
      const seconds = query.state.data?.expires_in ?? 0;
      return seconds > 0 ? Math.max(0, seconds - 60) * 1000 : Infinity;
    },
  });
}

function Published({ output, agents }: { output: RunOutput; agents?: AgentManifest[] }) {
  const link = useLink(output.id);
  const toast = useToast();
  const url = link.data?.url ?? null;

  return (
    <Card padding="compact" className="grid gap-2">
      <p className="text-body-sm font-medium text-text">{agentTitle(output.agent_type, agents)}</p>
      {link.isPending ? (
        <Skeleton className="h-4 w-3/4" />
      ) : url ? (
        <>
          <p className="truncate font-mono text-mono-sm text-text-muted" title={url}>
            {url}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              icon={<Copy size={14} aria-hidden />}
              onClick={() => copy(url, "Link copied.", toast)}
            >
              Copy link
            </Button>
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-7 items-center gap-1.5 rounded-sm border border-border-strong px-2.5 text-caption text-text hover:bg-surface-hover hover:no-underline"
            >
              <ExternalLink size={14} aria-hidden /> Open
            </a>
          </div>
        </>
      ) : (
        <p className="text-body-sm text-text-muted">This link isn&apos;t available.</p>
      )}
    </Card>
  );
}

function FileCard({ output, agents }: { output: RunOutput; agents?: AgentManifest[] }) {
  const link = useLink(output.id);
  const url = link.data?.url ?? null;

  return (
    <Card padding="compact" className="grid content-start gap-2">
      <div className="grid h-32 place-items-center overflow-hidden rounded-sm bg-bg-sunken">
        {link.isPending ? (
          <Skeleton className="h-full w-full" />
        ) : url && isVideo(output) ? (
          <video controls src={url} className="h-full w-full" aria-label={output.filename ?? "Video"} />
        ) : url && isImage(output) ? (
          <img src={url} alt={output.filename ?? "Image"} className="h-full w-full object-contain" />
        ) : (
          <FileText size={28} aria-hidden className="text-text-subtle" />
        )}
      </div>

      <p className="truncate text-body-sm font-medium text-text" title={output.filename ?? undefined}>
        {output.filename ?? "Untitled file"}
      </p>
      <p className="flex flex-wrap items-center gap-1.5 text-caption text-text-muted">
        <span>{kindLabel(output)}</span>
        {output.bytes != null && <span>· {formatBytes(output.bytes)}</span>}
        <span className="flex items-center gap-1">
          · <Sparkles size={11} aria-hidden /> Generated by {agentTitle(output.agent_type, agents)}
        </span>
      </p>

      {link.isError ? (
        <p className="text-body-sm text-status-failed-fg">
          Couldn&apos;t prepare this download. {link.error instanceof ApiError ? link.error.message : ""}
        </p>
      ) : (
        // Files are served from another origin (the app is on :5173, files on :8000, and in
        // production from the storage host), so the browser ignores `download` — without a target
        // the click would navigate away and play the video where the app used to be. An anchor
        // with no href is not focusable, which is how this is disabled: `pointer-events-none`
        // stops a mouse but leaves it in the tab order.
        <a
          {...(url ? { href: url, target: "_blank", rel: "noreferrer", download: output.filename ?? true } : {})}
          aria-disabled={url === null || undefined}
          className={`inline-flex h-7 items-center justify-center gap-1.5 rounded-sm bg-surface-inverse px-2.5 text-caption text-text-inverse hover:opacity-90 hover:no-underline ${
            url === null ? "pointer-events-none opacity-40" : ""
          }`}
        >
          <Download size={14} aria-hidden /> Download
        </a>
      )}
    </Card>
  );
}

function Written({ output, agents }: { output: RunOutput; agents?: AgentManifest[] }) {
  const link = useLink(output.id);
  const toast = useToast();
  const text = link.data?.text ?? null;

  return (
    <Card padding="compact" className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-body-md font-medium text-text">{agentTitle(output.agent_type, agents)}</h3>
        <span className="flex-1" />
        {text && (
          <Button
            size="sm"
            icon={<Copy size={14} aria-hidden />}
            onClick={() => copy(text, "Copied.", toast)}
          >
            Copy text
          </Button>
        )}
      </div>
      {link.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : text ? (
        <p className="max-h-64 max-w-[68ch] overflow-y-auto whitespace-pre-wrap text-body-md text-text">{text}</p>
      ) : (
        <p className="text-body-sm text-text-muted">There is nothing in this one.</p>
      )}
    </Card>
  );
}

/** A run a person stopped is recorded as `failed`; it is never reported as one (§2 rule 7). */
function wasRejected(run: RunState | undefined): boolean {
  if (run?.status !== "failed") return false;
  return (run.nodes ?? []).some((node) => stepError(node.error_message)?.rejected === true);
}

function emptyMessage(run: RunState | undefined): string {
  if (!run) return "Files will appear here as each step finishes.";
  if (!TERMINAL_RUN_STATUSES.has(run.status)) return "Files will appear here — each one shows up as soon as its step finishes.";
  if (wasRejected(run)) return "You stopped this run, so nothing was made after that point.";
  if (run.status === "failed") return "No files were made. The run stopped before anything was produced.";
  return "This run didn't produce any files.";
}

export function OutputsPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => endpoints.runState(runId),
    retry: (count, error) => !("status" in error && error.status === 404) && count < 3,
    // "each one shows up as soon as its step finishes" is a promise, so it has to be kept.
    refetchInterval: (query) => (query.state.data && TERMINAL_RUN_STATUSES.has(query.state.data.status) ? false : POLL_MS),
    refetchIntervalInBackground: true,
  });
  const live = run.data != null && !TERMINAL_RUN_STATUSES.has(run.data.status);
  const outputs = useQuery({
    queryKey: ["run-outputs", runId],
    queryFn: () => endpoints.runOutputs(runId),
    refetchInterval: live ? POLL_MS : false,
  });
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: endpoints.catalog, staleTime: 5 * 60_000 });

  const again = useMutation({
    mutationFn: () => endpoints.run(run.data!.workflow_id),
    onSuccess: (created) => navigate(`/runs/${created.run_id}`),
    onError: (error) =>
      toast({
        variant: "error",
        message: validationFrom(error)
          ? "This workflow needs fixing before it can run again. Open it to see what's wrong."
          : error instanceof ApiError
            ? error.message
            : "Couldn't start the run.",
      }),
  });

  if (run.isError && "status" in run.error && run.error.status === 404) {
    return <NotFoundState message="That run doesn't exist." />;
  }

  const items = outputs.data ?? [];
  const published = items.filter((o) => o.kind === "url");
  const files = items.filter((o) => o.kind === "file");
  const written = items.filter((o) => o.kind === "text");
  const agents = catalog.data;

  return (
    <AppShell crumbs={[{ label: "Workflows", to: "/workflows" }, { label: "Run", to: `/runs/${runId}` }, { label: "Files" }]}>
      <PageBody>
        <header className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-heading-lg text-text">Files</h1>
            {run.data && <StatusChip meta={wasRejected(run.data) ? rejectedMeta : runStatusMeta[run.data.status]} />}
            {run.data?.completed_at && run.data.started_at && (
              <span className="font-mono text-mono-sm text-text-muted">
                {formatDuration((Date.parse(run.data.completed_at) - Date.parse(run.data.started_at)) / 1000)}
              </span>
            )}
            {run.data && TERMINAL_RUN_STATUSES.has(run.data.status) && (
              <Button className="ml-auto" variant="primary" onClick={() => again.mutate()} loading={again.isPending}>
                Run this workflow again
              </Button>
            )}
          </div>
          {/* The run itself is one click away; the steps list lives there (§21 S-05). */}
          <nav className="flex gap-4 border-b border-border text-body-sm">
            <Link to={`/runs/${runId}`} className="px-1 pb-2 text-text-muted hover:text-text">
              Overview
            </Link>
            <span aria-current="page" className="border-b-2 border-text px-1 pb-2 font-medium text-text">
              Files{items.length > 0 ? ` ${items.length}` : ""}
            </span>
          </nav>
        </header>

        {run.isError && <Banner variant="error">Couldn&apos;t load this run.</Banner>}
        {outputs.isError && <Banner variant="error">Couldn&apos;t load what this run made.</Banner>}

        {outputs.isPending && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-busy>
            <Skeleton className="h-56 w-full" />
            <Skeleton className="h-56 w-full" />
            <Skeleton className="h-56 w-full" />
          </div>
        )}

        {!outputs.isPending && items.length === 0 && (
          <EmptyState title="Nothing here yet" body={emptyMessage(run.data)} />
        )}

        {published.length > 0 && (
          <section className="grid gap-3" aria-label="Published">
            <h2 className="text-heading-sm text-text">Published</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {published.map((output) => (
                <Published key={output.id} output={output} agents={agents} />
              ))}
            </div>
          </section>
        )}

        {files.length > 0 && (
          <section className="grid gap-3" aria-label="Files">
            <h2 className="text-heading-sm text-text">{pluralise(files.length, "file")}</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {files.map((output) => (
                <FileCard key={output.id} output={output} agents={agents} />
              ))}
            </div>
          </section>
        )}

        {written.length > 0 && (
          <section className="grid gap-3" aria-label="Text">
            <h2 className="text-heading-sm text-text">Text</h2>
            <div className="grid gap-3">
              {written.map((output) => (
                <Written key={output.id} output={output} agents={agents} />
              ))}
            </div>
          </section>
        )}
      </PageBody>
    </AppShell>
  );
}
