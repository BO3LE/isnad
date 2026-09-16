import { configSummary, graphsEqual, refuseConnection, snapToGrid, stepNumbers } from "./graph";

const edge = (source: string, target: string) => ({ id: `${source}-${target}`, source, target });

describe("refuseConnection (§15.3)", () => {
  it("allows a normal forward connection", () => {
    expect(refuseConnection([], "researcher", "writer")).toBeNull();
  });

  it("refuses a node connecting to itself", () => {
    expect(refuseConnection([], "writer", "writer")).toBe("self");
  });

  it("refuses the same connection twice", () => {
    expect(refuseConnection([edge("a", "b")], "a", "b")).toBe("duplicate");
  });

  it("refuses a direct loop", () => {
    expect(refuseConnection([edge("a", "b")], "b", "a")).toBe("cycle");
  });

  it("refuses a loop several steps long", () => {
    const chain = [edge("a", "b"), edge("b", "c"), edge("c", "d")];
    expect(refuseConnection(chain, "d", "a")).toBe("cycle");
    // Joining two ends of a fork is not a loop — it is a diamond, which is legitimate.
    expect(refuseConnection([edge("a", "b"), edge("a", "c")], "b", "c")).toBeNull();
  });
});

describe("stepNumbers (§15.2)", () => {
  it("numbers a straight chain in order", () => {
    const steps = stepNumbers(["a", "b", "c"], [edge("a", "b"), edge("b", "c")]);
    expect([steps.get("a"), steps.get("b"), steps.get("c")]).toEqual([1, 2, 3]);
  });

  it("gives parallel branches the same step", () => {
    const steps = stepNumbers(["a", "b", "c"], [edge("a", "b"), edge("a", "c")]);
    expect(steps.get("b")).toBe(2);
    expect(steps.get("c")).toBe(2);
  });

  it("waits for every input before numbering a join", () => {
    const steps = stepNumbers(["a", "b", "c", "d"], [edge("a", "b"), edge("a", "c"), edge("b", "d"), edge("c", "d")]);
    expect(steps.get("d")).toBe(3);
  });

  it("numbers unconnected nodes as step 1", () => {
    const steps = stepNumbers(["a", "b"], []);
    expect([steps.get("a"), steps.get("b")]).toEqual([1, 1]);
  });

  // A cycle can only arrive from the server; the canvas refuses to create one. It must not hang.
  it("leaves nodes in a cycle unnumbered instead of looping forever", () => {
    const steps = stepNumbers(["a", "b"], [edge("a", "b"), edge("b", "a")]);
    expect(steps.get("a")).toBeUndefined();
    expect(steps.get("b")).toBeUndefined();
  });
});

describe("snapToGrid", () => {
  it("snaps to the nearest 16 px", () => {
    expect(snapToGrid(0)).toBe(0);
    expect(snapToGrid(7)).toBe(0);
    expect(snapToGrid(9)).toBe(16);
    expect(snapToGrid(-9)).toBe(-16);
  });
});

describe("configSummary (§15.2)", () => {
  it("joins up to three values", () => {
    expect(configSummary({ length: "Medium", style: "Informative", format: "Blog post", extra: "ignored" })).toBe(
      "Medium · Informative · Blog post",
    );
  });

  it("skips empty values rather than printing gaps", () => {
    expect(configSummary({ topic: "Solar", notes: "", sources: null })).toBe("Solar");
  });

  it("is empty for an unconfigured node", () => {
    expect(configSummary({})).toBe("");
    expect(configSummary(null)).toBe("");
  });
});

describe("graphsEqual", () => {
  it("stops autosave firing when nothing changed", () => {
    const graph = { nodes: [{ id: "a", agent_type: "writer", position: { x: 0, y: 0 }, configuration: {}, requires_approval: false }], edges: [] };
    expect(graphsEqual(graph, structuredClone(graph))).toBe(true);
    expect(graphsEqual(graph, { ...graph, edges: [{ id: "e", source: "a", target: "b" }] })).toBe(false);
  });
});
