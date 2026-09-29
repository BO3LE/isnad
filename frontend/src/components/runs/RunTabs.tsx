import { Link } from "react-router-dom";

// The tab bar P-06, P-08 and P-09 share (FRONTEND-PAGES-PLAN.md §C: "P-06 to P-09 share a run
// header and tab bar"). It was written inline on the Outputs page when that was the only screen
// with one; Logs makes it the second, so it lives here rather than being copied.
//
// The current tab is not a link: there is nowhere to go, and a link to the page you are on is a
// trap for anyone navigating by keyboard or screen reader.

export type RunTab = "overview" | "logs" | "files";

export interface RunTabsProps {
  runId: string;
  current: RunTab;
  /** Shown beside "Files" once the count is known; a run that made nothing shows no number. */
  fileCount?: number;
}

const CURRENT = "border-b-2 border-text px-1 pb-2 font-medium text-text";
const OTHER = "px-1 pb-2 text-text-muted hover:text-text";

export function RunTabs({ runId, current, fileCount }: RunTabsProps) {
  const tabs: { id: RunTab; label: string; to: string }[] = [
    { id: "overview", label: "Overview", to: `/runs/${runId}` },
    { id: "logs", label: "Logs", to: `/runs/${runId}/logs` },
    { id: "files", label: fileCount ? `Files ${fileCount}` : "Files", to: `/runs/${runId}/outputs` },
  ];

  return (
    <nav aria-label="This run" className="flex gap-4 border-b border-border text-body-sm">
      {tabs.map((tab) =>
        tab.id === current ? (
          <span key={tab.id} aria-current="page" className={CURRENT}>
            {tab.label}
          </span>
        ) : (
          <Link key={tab.id} to={tab.to} className={OTHER}>
            {tab.label}
          </Link>
        ),
      )}
    </nav>
  );
}
