import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Skeleton } from "@/design-system/components/Skeleton";
import { Tabs } from "@/design-system/components/Tabs";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { formatBytes } from "@/lib/format";
import { endpoints, type AgentManifest, type RunOutput } from "@/lib/api";

// DESIGN-SYSTEM.md §21 S-06 — "see exactly what will be published and decide". Only what exists
// gets a tab: a run that made no video has no Video tab, rather than an empty one.
//
// Nothing here knows an agent. What an output *is* comes from its kind and its media type, and
// whose it is comes from the catalog — so a seventh agent's file previews like any other (AT-12).

function isImage(output: RunOutput): boolean {
  return output.kind === "file" && (output.mime_type ?? "").startsWith("image/");
}

function isVideo(output: RunOutput): boolean {
  return output.kind === "file" && (output.mime_type ?? "").startsWith("video/");
}

/** What to call this output's tab: whose it is, then what it is. */
function label(output: RunOutput, agents?: AgentManifest[]): string {
  const who = agentTitle(output.agent_type, agents);
  if (output.kind === "url") return `${who} · link`;
  if (output.filename) return `${who} · ${output.filename}`;
  return `${who} · text`;
}

function Loading() {
  return (
    <div className="grid gap-2" aria-busy>
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  );
}

function One({ output }: { output: RunOutput }) {
  // What a run produced never changes, so this is fetched once. Without it every tab switch
  // remounts this component and refetches — re-minting a download URL to show the same file.
  const link = useQuery({
    queryKey: ["output", output.id],
    queryFn: () => endpoints.output(output.id),
    staleTime: Infinity,
  });

  if (link.isPending) return <Loading />;
  if (link.isError) {
    return (
      <p className="text-body-sm text-status-failed-fg">
        Couldn&apos;t open this one. {link.error instanceof Error ? link.error.message : ""}
      </p>
    );
  }

  const { url, text } = link.data;

  if (text != null) {
    return (
      // 68ch, the width §21 gives the article so it stays readable.
      <div className="grid gap-2">
        <p className="flex items-center gap-1.5 text-caption text-text-muted">
          <Sparkles size={12} aria-hidden /> Generated
        </p>
        <p className="max-h-72 max-w-[68ch] overflow-y-auto whitespace-pre-wrap text-body-md text-text">{text}</p>
      </div>
    );
  }

  if (!url) return <p className="text-body-sm text-text-muted">There is nothing in this one.</p>;

  if (isVideo(output)) {
    return (
      <video controls src={url} className="max-h-72 w-full rounded-sm bg-bg-sunken" aria-label={output.filename ?? "Video"}>
        <a href={url}>Download the video</a>
      </video>
    );
  }

  if (isImage(output)) {
    return <img src={url} alt={output.filename ?? "Image"} className="max-h-72 rounded-sm object-contain" />;
  }

  // Anything else — a PDF, a document, a published link — is offered rather than rendered.
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-body-md text-interactive underline">
      {output.kind === "url" ? url : `Open ${output.filename ?? "this file"}`}
    </a>
  );
}

export interface OutputPreviewProps {
  runId: string | null;
  agents?: AgentManifest[];
}

export function OutputPreview({ runId, agents }: OutputPreviewProps) {
  const outputs = useQuery({
    queryKey: ["run-outputs", runId],
    queryFn: () => endpoints.runOutputs(runId!),
    enabled: runId !== null,
  });
  const [shown, setShown] = useState<string | null>(null);
  const items = useMemo(() => outputs.data ?? [], [outputs.data]);

  // Land on the first thing the run made, and never on one that has gone away.
  useEffect(() => {
    const first = items[0];
    if (first && !items.some((item) => item.id === shown)) setShown(first.id);
  }, [items, shown]);

  if (outputs.isPending && runId !== null) {
    return (
      <section className="grid gap-2 rounded-md border border-border bg-surface p-4" aria-label="Preview">
        <Loading />
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="grid gap-1 rounded-md border border-dashed border-border-strong bg-bg-sunken p-4" aria-label="Preview">
        <p className="text-body-md font-medium text-text">Nothing to show yet</p>
        <p className="text-body-sm text-text-muted">This run hasn&apos;t produced a file or any text yet.</p>
      </section>
    );
  }

  const current = items.find((item) => item.id === shown) ?? items[0];
  if (!current) return null;

  return (
    <section className="grid gap-3 rounded-md border border-border bg-surface p-4" aria-label="Preview">
      <Tabs
        label="What this run made"
        tabs={items.map((item) => ({ id: item.id, label: label(item, agents) }))}
        value={current.id}
        onChange={setShown}
      />
      <div className="grid gap-1">
        <One key={current.id} output={current} />
        {current.bytes != null && <p className="text-caption text-text-muted">{formatBytes(current.bytes)}</p>}
      </div>
    </section>
  );
}
