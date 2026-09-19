import { Link } from "react-router-dom";
import { Badge } from "@/design-system/components/Badge";
import { StatusChip } from "@/design-system/status/StatusChip";
import { runStatusMeta } from "@/design-system/status/statusMeta";
import { formatRelativeTime, pluralise } from "@/lib/format";
import type { RunStatus } from "@/lib/api";

// DESIGN-SYSTEM.md §15.6 — 32 px, body-sm muted, separated by " · ".
export interface CanvasStatusBarProps {
  steps: number;
  validation: { state: "unknown" | "valid" | "issues"; count: number; onOpen: () => void };
  lastRun?: { id: string; status: RunStatus; createdAt: string } | null;
  zoom: number;
  mockAgents: boolean;
}

const Dot = () => (
  <span aria-hidden className="text-text-subtle">
    ·
  </span>
);

export function CanvasStatusBar({ steps, validation, lastRun, zoom, mockAgents }: CanvasStatusBarProps) {
  return (
    <footer className="flex h-8 shrink-0 items-center gap-2 border-t border-border bg-surface px-3 text-body-sm text-text-muted">
      <span>{pluralise(steps, "step")}</span>
      <Dot />

      {validation.state === "valid" && <span className="text-status-success-fg">✓ Valid</span>}
      {validation.state === "issues" && (
        <button type="button" onClick={validation.onOpen} className="text-status-failed-fg hover:underline">
          {pluralise(validation.count, "issue")}
        </button>
      )}
      {validation.state === "unknown" && <span>Not validated</span>}

      {lastRun && (
        <>
          <Dot />
          <span className="flex items-center gap-1.5">
            Last run
            <StatusChip meta={runStatusMeta[lastRun.status]} />
            {formatRelativeTime(lastRun.createdAt)}
          </span>
          <Link to={`/runs/${lastRun.id}`} className="text-interactive hover:underline">
            View run
          </Link>
        </>
      )}

      <span className="flex-1" />
      <span className="font-mono text-mono-sm tabular-nums">{Math.round(zoom * 100)}%</span>
      {mockAgents && <Badge>Mock agents</Badge>}
    </footer>
  );
}
