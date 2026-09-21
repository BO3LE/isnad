import type { LogEntry, NodeStatus } from "./api";

// P-08's reading of what the worker recorded (DESIGN-SYSTEM §21 S-07, §16.5).
//
// The worker keeps one row per step and updates it in place, appending each failure to
// `error_message` behind an `[attempt N]` marker (worker/store.py). So the attempt history is
// real, but only as text: there are no per-attempt timestamps or durations anywhere, which is
// gap 19 in FRONTEND-PAGES-PLAN.md. This file reads exactly what is there and no more.

/**
 * Mirrors `contracts.run.MAX_RETRIES`. It is not in the generated types — the contract expresses
 * it as a field maximum, which openapi-typescript drops — so it is duplicated here and nowhere
 * else. If the orchestrator's limit changes, this is the line that has to change with it.
 */
export const MAX_RETRIES = 3;

export interface Attempt {
  /** 1-based, as the worker writes it. */
  number: number;
  text: string;
}

/**
 * The attempts behind one step's `error_message`, oldest first.
 *
 * A message with no marker is one unnumbered attempt rather than nothing — older rows and any
 * error written outside the retry path look like that, and dropping them would hide the only
 * explanation the step has.
 */
export function attemptsOf(message: string | null | undefined): Attempt[] {
  if (!message) return [];
  const out: Attempt[] = [];
  for (const line of message.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const marked = /^\[attempt (\d+)\]\s*(.*)$/.exec(trimmed);
    if (marked) {
      out.push({ number: Number(marked[1]), text: (marked[2] ?? "").trim() });
    } else if (out.length > 0) {
      // A continuation line of the attempt above — an agent's error can be several lines.
      const last = out[out.length - 1]!;
      last.text = last.text ? `${last.text} ${trimmed}` : trimmed;
    } else {
      out.push({ number: out.length + 1, text: trimmed });
    }
  }
  return out;
}

/**
 * What the orchestrator waited before retry `n` — `2**n` seconds, before jitter.
 *
 * Narrated with "about" because `backoff_delay` adds `random()` (worker/orchestrator.py), so the
 * exact wait is never what a table would print.
 */
export function backoffSeconds(retry: number): number {
  return 2 ** retry;
}

/**
 * "Retrying 2/3" — §16.5's wording for a step that is between attempts.
 *
 * Clamped at both ends. The orchestrator increments `retry_count` before it writes the `retrying`
 * status (worker/orchestrator.py), so 0 never reaches here from a real run and neither does a
 * number above the maximum — but "Retrying 0/3" and "Retrying 4/3" are nonsense a reader would
 * have to interpret, and one expression is cheaper than trusting the producer forever.
 */
export function retryLabel(retryCount: number): string {
  return `Retrying ${Math.min(Math.max(retryCount, 1), MAX_RETRIES)}/${MAX_RETRIES}`;
}

/** How long the orchestrator waits before attempt `n + 1`, narrated for the attempt timeline. */
export function retryWaitLabel(attemptNumber: number): string {
  const retry = Math.min(attemptNumber, MAX_RETRIES);
  return `Retry ${retry} of ${MAX_RETRIES}, about ${backoffSeconds(retry)}s later.`;
}

/**
 * What finally stopped the step, for the table's narrow error column.
 *
 * The *last* attempt, not the first: earlier attempts are the ones that were retried past. This
 * overlaps `stepError` in runPlayback.ts, which answers the same question for the run monitor and
 * additionally reports whether the step was rejected; the difference here is that a wrapped error
 * is folded back onto one line so it fits a table cell.
 */
export function lastAttemptText(message: string | null | undefined): string {
  const attempts = attemptsOf(message);
  const last = attempts[attempts.length - 1];
  return last?.text ?? "";
}

export interface LogFilter {
  text: string;
  statuses: NodeStatus[];
  agents: string[];
}

export const NO_FILTER: LogFilter = { text: "", statuses: [], agents: [] };

export function isFiltered(filter: LogFilter): boolean {
  return filter.text.trim() !== "" || filter.statuses.length > 0 || filter.agents.length > 0;
}

/**
 * Rows the filter keeps. Text matches the agent's *displayed* title as well as its type, because
 * someone reading "Publisher" on the screen will type "Publisher", not "publisher".
 */
export function applyFilter(rows: LogEntry[], filter: LogFilter, titleOf: (agentType: string) => string): LogEntry[] {
  const needle = filter.text.trim().toLowerCase();
  return rows.filter((row) => {
    if (filter.statuses.length > 0 && !filter.statuses.includes(row.status)) return false;
    if (filter.agents.length > 0 && !filter.agents.includes(row.agent_type)) return false;
    if (!needle) return true;
    const haystack = [titleOf(row.agent_type), row.agent_type, row.error_message ?? ""].join(" ").toLowerCase();
    return haystack.includes(needle);
  });
}

/** The CSV's columns, in order, exactly as §21 S-07 specifies them. */
export const CSV_COLUMNS = [
  "run_id",
  "node_id",
  "agent_type",
  "status",
  "started_at",
  "completed_at",
  "duration_ms",
  "retry_count",
  "error_message",
] as const;

/** RFC 4180: quote when the value could otherwise break a row, and double any quote inside it. */
function cell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function iso(value: string | null | undefined): string {
  if (!value) return "";
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? "" : at.toISOString();
}

/**
 * The rows as they were recorded, not as they are displayed: raw column names, ISO 8601 in UTC,
 * and the whole `error_message` including every attempt — this file goes into the Results &
 * Metrics tables (§21 S-07), where a localised timestamp would be useless.
 */
export function toCsv(rows: LogEntry[]): string {
  const lines = [CSV_COLUMNS.join(",")];
  for (const row of rows) {
    lines.push(
      [
        row.run_id,
        row.node_id,
        row.agent_type,
        row.status,
        iso(row.started_at),
        iso(row.completed_at),
        row.duration_ms == null ? "" : String(row.duration_ms),
        String(row.retry_count),
        row.error_message ?? "",
      ]
        .map(cell)
        .join(","),
    );
  }
  // A trailing newline: POSIX tools treat a file without one as a truncated last record.
  return `${lines.join("\n")}\n`;
}
