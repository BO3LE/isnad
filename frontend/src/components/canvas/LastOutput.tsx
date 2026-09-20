import { useState } from "react";
import { Tabs } from "@/design-system/components/Tabs";
import { formatBytes, formatRelativeTime } from "@/lib/format";
import { OutputBody, OutputLoading } from "@/components/runs/OutputPreview";
import type { RunOutput } from "@/lib/api";
import type { LastOutputState } from "./useLastOutput";

// S-04's second tab (DESIGN-SYSTEM §21 S-04, §17.6) — what this step produced the last time the
// workflow ran, read-only. §17.6 shows the tab "only if one exists", so the drawer asks first and
// offers the tab only when there is something behind it; an empty tab was worth nothing.
//
// The rendering is `OutputBody`, the same one the approval dialog uses, so a seventh agent's output
// previews here without this file knowing anything about it (AT-12).

/**
 * What to call one of this step's outputs. The drawer's header already says whose it is.
 *
 * `kind` decides, not the filename: a file whose `storage_path` is null arrives with no filename
 * (api/routers/runs.py names a file by the last segment of its path), and calling that "Text"
 * would be a lie about what it is. Two text outputs from one step still share a label — naming
 * them needs the output-field column that `db/` has yet to add.
 */
function label(output: RunOutput): string {
  if (output.kind === "url") return "Link";
  if (output.kind === "file") return output.filename ?? "File";
  return "Text";
}

export function LastOutput({ state }: { state: LastOutputState }) {
  const { outputs, ranAt, isPending, isError } = state;
  const [shown, setShown] = useState<string | null>(null);

  const current = outputs.find((output) => output.id === shown) ?? outputs[0];
  // Past a week this is an absolute date, not "3h ago", so the sentence has to read either way;
  // an unparseable date gives "", which would leave "From the last run, ." on the screen.
  const when = ranAt ? formatRelativeTime(ranAt) : "";

  // What we already have beats what we are fetching. React Query keeps the last good outputs when
  // a refetch fails — and the drawer starts one every time it opens — so testing `isError` first
  // would replace a preview someone is reading with a complaint about the refresh.
  if (!current) {
    if (isPending) return <OutputLoading />;
    if (isError) {
      return <p className="text-body-sm text-status-failed-fg">Couldn&apos;t load what this step made last time.</p>;
    }
    return null;
  }

  return (
    <div className="grid gap-3">
      {when && (
        <p className="text-caption text-text-muted">
          From the last run, <time dateTime={ranAt ?? undefined}>{when}</time>.
        </p>
      )}

      {/* One output needs no tabs; a step that made several — a file and its text — does. */}
      {outputs.length > 1 && (
        <Tabs
          label="What this step made"
          tabs={outputs.map((output) => ({ id: output.id, label: label(output) }))}
          value={current.id}
          onChange={setShown}
        />
      )}

      <div className="grid gap-1">
        <OutputBody key={current.id} output={current} />
        {current.bytes != null && <p className="text-caption text-text-muted">{formatBytes(current.bytes)}</p>}
      </div>
    </div>
  );
}
