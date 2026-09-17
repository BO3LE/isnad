import type { NodeStatus, RunState, RunStatus } from "./api";

// Run mode on the canvas (UX-SPEC §6): the chain lights up one handover at a time.
//
// The worker can finish several steps between two polls — mock agents take milliseconds — and a
// run that jumps from "queued" to "needs approval" shows nothing moving from one agent to the
// next. So the canvas plays the server's state forward at most one change per tick, in run order,
// and a step always shows as running before it shows as done. Real agents take seconds or minutes
// and are never held back; the display only ever moves towards what the server says.

export type Shown = Record<string, NodeStatus>;

/** A tick's worth of time between two visible changes. */
export const PLAYBACK_TICK_MS = 900;

const FINISHED: ReadonlySet<NodeStatus> = new Set(["success", "failed", "awaiting_approval", "skipped"]);

export function serverStatuses(run: RunState | undefined): Shown {
  return Object.fromEntries((run?.nodes ?? []).map((node) => [node.node_id, node.status]));
}

/** One step of playback: the first step (in run order) that differs moves one stage closer. */
export function advance(shown: Shown, server: Shown, order: string[]): Shown {
  for (const id of order) {
    const target = server[id];
    const current = shown[id] ?? "pending";
    if (target === undefined || target === current) continue;
    // A step is seen working before it is done — including one that was just approved. A skipped
    // step never ran, and a rejected one stops where it stood.
    const startsWork = current === "pending" ? FINISHED.has(target) && target !== "skipped" : current === "awaiting_approval" && target === "success";
    if (startsWork) return { ...shown, [id]: "running" };
    return { ...shown, [id]: target };
  }
  return shown;
}

/** Cancelling is the user's own action — show it at once rather than playing it out. */
export function catchUp(server: Shown): Shown {
  return { ...server };
}

export function caughtUp(shown: Shown, server: Shown): boolean {
  return Object.entries(server).every(([id, status]) => (shown[id] ?? "pending") === status);
}

/** The run's status as the canvas shows it: still "running" until playback reaches the server. */
export function shownRunStatus(run: RunState | undefined, shown: Shown): RunStatus | null {
  if (!run) return null;
  if (run.status === "queued") return "queued";
  return caughtUp(shown, serverStatuses(run)) ? run.status : "running";
}

export function countDone(shown: Shown): number {
  return Object.values(shown).filter((status) => status === "success").length;
}

/** How the worker records a step the user rejected (worker/orchestrator.py). */
const REJECTED_MESSAGE = "Rejected by reviewer.";

/**
 * A step's error as a person should read it. The worker's store prefixes every message with
 * "[attempt N] " (worker/store.py) — bookkeeping, not wording — and a rejection is the user's own
 * decision, never a failure (UX-SPEC §7).
 */
export function stepError(message: string | null | undefined): { text: string; rejected: boolean } | null {
  if (!message) return null;
  const text = message.replace(/^\[attempt \d+\]\s*/, "");
  return { text, rejected: text === REJECTED_MESSAGE };
}

export const ACTIVE_RUN: ReadonlySet<RunStatus> = new Set(["queued", "running", "awaiting_approval"]);
