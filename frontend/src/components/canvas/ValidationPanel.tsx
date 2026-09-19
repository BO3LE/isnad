import { CircleCheck, CircleX, TriangleAlert, X } from "lucide-react";
import { useEffect } from "react";
import { Button } from "@/design-system/components/Button";
import { IconButton } from "@/design-system/components/IconButton";
import { pluralise } from "@/lib/format";
import type { ValidationResult } from "@/lib/api";

// DESIGN-SYSTEM.md §15.5 — docked above the status bar, listing what `POST /workflows/{id}/validate`
// found. UX-SPEC §4.4: the server owns the wording. Every message is rendered exactly as it arrives —
// never shortened, prefixed, re-cased or re-punctuated. If a message reads badly, it is fixed in
// `api/src/api/services/validation.py`, not here.

/** How long "Ready to run" stays before the panel closes itself (§15.5). */
export const READY_DISMISS_MS = 2000;

export interface ValidationPanelProps {
  result: ValidationResult;
  /** The step's title, from the catalog — or null once it has been deleted. */
  titleOf: (nodeId: string) => string | null;
  onGoToStep: (nodeId: string) => void;
  onClose: () => void;
}

export function ValidationPanel({ result, titleOf, onGoToStep, onClose }: ValidationPanelProps) {
  const issues = result.issues ?? [];
  const ready = issues.length === 0;

  // Nothing left to fix: say so, then get out of the way.
  useEffect(() => {
    if (!ready) return;
    const timer = window.setTimeout(onClose, READY_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [ready, onClose]);

  const heading = ready
    ? "Ready to run"
    : result.valid
      ? pluralise(issues.length, "warning")
      : `${pluralise(issues.length, "issue")} to fix before running`;

  return (
    <section
      aria-label="Validation"
      className="flex max-h-[40vh] shrink-0 flex-col border-t border-border bg-surface"
    >
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        {ready ? (
          <CircleCheck aria-hidden className="size-4 shrink-0 text-status-success-solid" />
        ) : (
          <TriangleAlert
            aria-hidden
            className={`size-4 shrink-0 ${result.valid ? "text-status-retrying-solid" : "text-status-failed-solid"}`}
          />
        )}
        <h2 className={`text-body-sm font-medium ${ready ? "text-status-success-fg" : "text-text"}`}>{heading}</h2>
        <span className="flex-1" />
        <IconButton size="sm" label="Close validation" icon={<X className="size-4" />} onClick={onClose} />
      </header>

      {issues.length > 0 && (
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {issues.map((issue, index) => {
            const warning = issue.severity === "warning";
            const title = issue.node_id ? titleOf(issue.node_id) : null;
            return (
              <li
                key={`${issue.code}-${issue.node_id ?? issue.edge_id ?? index}`}
                className="flex items-center gap-2 border-b border-border px-3 py-2 last:border-b-0"
              >
                {warning ? (
                  <TriangleAlert aria-hidden className="size-4 shrink-0 text-status-retrying-solid" />
                ) : (
                  <CircleX aria-hidden className="size-4 shrink-0 text-status-failed-solid" />
                )}
                {/* The server's words, verbatim. */}
                <p className="min-w-0 flex-1 text-body-sm text-text">{issue.message}</p>
                {issue.node_id && title && (
                  <Button size="sm" onClick={() => onGoToStep(issue.node_id!)}>
                    Go to {title}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
