import { useCallback, useRef, useState } from "react";
import type { Edge, Node } from "reactflow";

// DESIGN-SYSTEM.md §21 S-03 — "Undo/redo: local history of 50 graph changes."
const LIMIT = 50;

export interface GraphSnapshot<T> {
  nodes: Node<T>[];
  edges: Edge[];
}

/**
 * Undo/redo for the canvas.
 *
 * Only *structural* changes are committed: adding, deleting, connecting, duplicating. Dragging a
 * node fires a change per mouse move, so committing those would fill all 50 slots with one drag and
 * make Undo useless. The caller commits once the drag ends instead.
 */
export function useGraphHistory<T>(initial: GraphSnapshot<T>) {
  const past = useRef<GraphSnapshot<T>[]>([]);
  const future = useRef<GraphSnapshot<T>[]>([]);
  const [depth, setDepth] = useState({ undo: 0, redo: 0 });

  const sync = useCallback(() => {
    setDepth({ undo: past.current.length, redo: future.current.length });
  }, []);

  /** Record the state as it was *before* a change the caller is about to apply. */
  const commit = useCallback(
    (before: GraphSnapshot<T>) => {
      past.current = [...past.current.slice(-(LIMIT - 1)), before];
      future.current = [];
      sync();
    },
    [sync],
  );

  const undo = useCallback(
    (current: GraphSnapshot<T>): GraphSnapshot<T> | null => {
      const previous = past.current.pop();
      if (!previous) return null;
      future.current = [...future.current.slice(-(LIMIT - 1)), current];
      sync();
      return previous;
    },
    [sync],
  );

  const redo = useCallback(
    (current: GraphSnapshot<T>): GraphSnapshot<T> | null => {
      const next = future.current.pop();
      if (!next) return null;
      past.current = [...past.current.slice(-(LIMIT - 1)), current];
      sync();
      return next;
    },
    [sync],
  );

  const reset = useCallback(() => {
    past.current = [];
    future.current = [];
    sync();
  }, [sync]);

  void initial;
  return { commit, undo, redo, reset, canUndo: depth.undo > 0, canRedo: depth.redo > 0 };
}
