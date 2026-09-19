import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  CircleX,
  Clock,
  Hand,
  LoaderCircle,
  RotateCw,
  type LucideIcon,
} from "lucide-react";
import type { NodeStatus, RunStatus } from "@/lib/api";

// DESIGN-SYSTEM.md §16 — the single map every status surface reads from.
// Record<…> is exhaustive: adding a status in contracts/run.py breaks the type-check until it is designed here.

export type Tone = "pending" | "running" | "retrying" | "approval" | "success" | "failed" | "skipped" | "cancelled";

export interface StatusMeta {
  label: string;
  tone: Tone;
  icon: LucideIcon;
  spin?: boolean;
}

export const nodeStatusMeta: Record<NodeStatus, StatusMeta> = {
  pending: { label: "Pending", tone: "pending", icon: CircleDashed },
  running: { label: "Running", tone: "running", icon: LoaderCircle, spin: true },
  retrying: { label: "Retrying", tone: "retrying", icon: RotateCw },
  awaiting_approval: { label: "Needs approval", tone: "approval", icon: Hand },
  success: { label: "Done", tone: "success", icon: CircleCheck },
  failed: { label: "Failed", tone: "failed", icon: CircleX },
  skipped: { label: "Skipped", tone: "skipped", icon: CircleSlash },
};

export const runStatusMeta: Record<RunStatus, StatusMeta> = {
  queued: { label: "Queued", tone: "pending", icon: Clock },
  running: { label: "Running", tone: "running", icon: LoaderCircle, spin: true },
  awaiting_approval: { label: "Needs approval", tone: "approval", icon: Hand },
  succeeded: { label: "Succeeded", tone: "success", icon: CircleCheck },
  failed: { label: "Failed", tone: "failed", icon: CircleX },
  cancelled: { label: "Cancelled", tone: "cancelled", icon: Ban },
};

/** A person's "no" — shown apart from a technical failure (UX-SPEC §7). */
export const rejectedMeta: StatusMeta = { label: "Rejected by you", tone: "cancelled", icon: Ban };

export const TERMINAL_RUN_STATUSES: ReadonlySet<RunStatus> = new Set(["succeeded", "failed", "cancelled"]);
