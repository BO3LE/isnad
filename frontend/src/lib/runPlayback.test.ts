import type { NodeStatus, RunState } from "./api";
import { advance, caughtUp, countDone, shownRunStatus, stepError, type Shown } from "./runPlayback";

const order = ["r", "w", "v", "p"];

function playOut(server: Shown, from: Shown = {}): Shown[] {
  const frames: Shown[] = [];
  let shown = from;
  for (let i = 0; i < 20; i++) {
    const next = advance(shown, server, order);
    if (next === shown) break;
    frames.push(next);
    shown = next;
  }
  return frames;
}

describe("advance — a run plays one handover at a time", () => {
  it("shows each step running before it is done, in run order", () => {
    const server: Shown = { r: "success", w: "success", v: "success", p: "awaiting_approval" };
    const frames = playOut(server, { r: "pending", w: "pending", v: "pending", p: "pending" });
    expect(frames.map((f) => order.map((id) => f[id]?.[0]).join(""))).toEqual([
      "rppp",
      "sppp",
      "srpp",
      "sspp",
      "ssrp",
      "sssp",
      "sssr",
      "sssa",
    ]);
  });

  it("changes nothing once it has caught up", () => {
    const server: Shown = { r: "success", w: "running", v: "pending", p: "pending" };
    const done = playOut(server).at(-1)!;
    expect(caughtUp(done, server)).toBe(true);
    expect(advance(done, server, order)).toBe(done);
  });

  it("shows a skipped step as skipped straight away", () => {
    expect(advance({ r: "success", w: "pending" }, { r: "success", w: "skipped" }, order)).toEqual({ r: "success", w: "skipped" });
  });

  it("shows an approved step working before it is done", () => {
    expect(advance({ p: "awaiting_approval" }, { p: "success" }, order)).toEqual({ p: "running" });
  });

  it("stops a rejected step where it stood", () => {
    expect(advance({ p: "awaiting_approval" }, { p: "failed" }, order)).toEqual({ p: "failed" });
  });

  it("follows a retry as it happens", () => {
    expect(advance({ r: "running" }, { r: "retrying" }, order)).toEqual({ r: "retrying" });
  });
});

describe("shownRunStatus", () => {
  const run = (status: RunState["status"], nodes: [string, NodeStatus][]) =>
    ({
      id: "run",
      workflow_id: "wf",
      status,
      total_nodes: nodes.length,
      failed_nodes: 0,
      nodes: nodes.map(([node_id, status]) => ({ node_id, agent_type: "x", status, retry_count: 0 })),
    }) as RunState;

  it("stays running until playback reaches the gate", () => {
    const state = run("awaiting_approval", [["r", "success"], ["p", "awaiting_approval"]]);
    expect(shownRunStatus(state, { r: "running", p: "pending" })).toBe("running");
    expect(shownRunStatus(state, { r: "success", p: "awaiting_approval" })).toBe("awaiting_approval");
  });

  it("counts finished steps", () => {
    expect(countDone({ r: "success", w: "success", v: "running" })).toBe(2);
  });
});

describe("stepError", () => {
  it("drops the worker's attempt prefix", () => {
    expect(stepError("[attempt 3] Writer is missing input: notes")).toEqual({ text: "Writer is missing input: notes", rejected: false });
  });

  it("reads the attempt that actually stopped the step, not the whole retry history", () => {
    // worker/store.py appends a line per attempt instead of replacing the message.
    expect(stepError("[attempt 1] Upload timed out\n[attempt 2] Upload timed out\n[attempt 3] YouTube refused the file")).toEqual({
      text: "YouTube refused the file",
      rejected: false,
    });
  });

  it("recognises a rejection as the user's decision", () => {
    expect(stepError("[attempt 1] Rejected by reviewer.")).toEqual({ text: "Rejected by reviewer.", rejected: true });
  });

  it("still recognises a rejection after a step had already failed once", () => {
    expect(stepError("[attempt 1] Upload timed out\n[attempt 2] Rejected by reviewer.")).toEqual({
      text: "Rejected by reviewer.",
      rejected: true,
    });
  });

  it("has nothing to say without a message", () => {
    expect(stepError(null)).toBeNull();
    expect(stepError("   ")).toBeNull();
  });
});
