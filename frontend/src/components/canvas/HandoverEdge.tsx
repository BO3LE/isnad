import { memo } from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "reactflow";

// UX-SPEC §4.3 — a connection names what crosses it: "notes · sources". It answers "what does
// this arrow mean?", the question every first-time user asks, and makes the product's promise —
// every handoff visible — true while building, not only while a run plays.

export interface HandoverEdgeData {
  /** Output titles the target reads from the source. Empty means the connection can't work. */
  items: string[];
  /** "Writer" — for the warning when nothing crosses. */
  targetTitle: string;
  /** Hovered, or one of its steps is hovered or selected. A broken connection always shows. */
  emphasised: boolean;
  /** During a run: the handover happening now, one already made, or neither. */
  flow?: "active" | "done" | "idle";
}

export const HandoverEdge = memo(function HandoverEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  markerEnd,
}: EdgeProps<HandoverEdgeData>) {
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const items = data?.items ?? [];
  const flow = data?.flow;
  const broken = data !== undefined && items.length === 0 && flow === undefined;
  const active = flow === "active";
  const lit = selected || data?.emphasised === true || active;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: active
            ? "var(--status-running-solid)"
            : flow === "done"
              ? "var(--status-success-solid)"
              : broken
                ? "var(--status-failed-solid)"
                : lit
                  ? "var(--color-text)"
                  : "var(--color-border-strong)",
          strokeWidth: lit || flow === "done" ? 2 : 1.5,
          strokeDasharray: active ? "6 10" : broken ? "4 4" : undefined,
          // The work visibly travels from one step to the next (§16.4).
          animation: active ? "handover-flow 800ms linear infinite" : undefined,
        }}
      />
      {data && (broken || lit) && (
        <EdgeLabelRenderer>
          <span
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            className={`nodrag nopan pointer-events-none absolute z-canvas-controls max-w-[200px] truncate rounded-xs border px-1.5 py-0.5 font-mono text-mono-sm shadow-2 ${
              active
                ? "border-status-running-solid bg-status-running-bg text-status-running-fg"
                : broken
                  ? "border-status-failed-solid bg-status-failed-bg text-status-failed-fg"
                  : "border-border-strong bg-surface-raised text-text"
            }`}
            title={broken ? `${data.targetTitle} can't use anything from this step` : `Hands on ${items.join(", ")}`}
          >
            {broken ? "nothing it can use" : items.join(" · ")}
          </span>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
