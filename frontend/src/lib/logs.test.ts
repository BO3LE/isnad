import { applyFilter, attemptsOf, backoffSeconds, CSV_COLUMNS, lastAttemptText, retryLabel, retryWaitLabel, toCsv } from "./logs";
import type { LogEntry } from "./api";

// The parsing and the CSV are where this page can be wrong without looking wrong: an attempt that
// is silently dropped, or a file that a spreadsheet splits into the wrong columns.

const row = (over: Partial<LogEntry> = {}): LogEntry => ({
  id: "11111111-1111-4111-8111-111111111111",
  run_id: "22222222-2222-4222-8222-222222222222",
  node_id: "33333333-3333-4333-8333-333333333333",
  agent_type: "publisher",
  status: "failed",
  retry_count: 0,
  started_at: "2026-09-20T16:09:40.000Z",
  completed_at: "2026-09-20T16:11:12.000Z",
  duration_ms: 92000,
  error_message: null,
  ...over,
});

describe("attemptsOf", () => {
  it("reads each marked attempt in the order the worker appended them", () => {
    const attempts = attemptsOf("[attempt 1] Token revoked.\n[attempt 2] Token revoked.\n[attempt 3] Gave up.");
    expect(attempts).toEqual([
      { number: 1, text: "Token revoked." },
      { number: 2, text: "Token revoked." },
      { number: 3, text: "Gave up." },
    ]);
  });

  it("keeps an unmarked message rather than dropping it", () => {
    // Anything written outside the retry path has no marker. Returning [] here would leave the
    // expanded row blank for a step that failed with a perfectly good explanation.
    expect(attemptsOf("Something went wrong.")).toEqual([{ number: 1, text: "Something went wrong." }]);
  });

  it("folds a wrapped error back into the attempt it belongs to", () => {
    const attempts = attemptsOf("[attempt 1] Publisher is missing input:\n  title — Field required");
    expect(attempts).toEqual([{ number: 1, text: "Publisher is missing input: title — Field required" }]);
  });

  it("has nothing to say about a step that never failed", () => {
    expect(attemptsOf(null)).toEqual([]);
    expect(attemptsOf("")).toEqual([]);
    expect(attemptsOf("   \n  ")).toEqual([]);
  });
});

describe("lastAttemptText", () => {
  it("shows what actually stopped the step, not its first stumble", () => {
    // The table has one line for the error, and the last attempt is the one that ended the run.
    expect(lastAttemptText("[attempt 1] Rate limited.\n[attempt 2] Token revoked.")).toBe("Token revoked.");
  });

  it("is empty when nothing failed", () => {
    expect(lastAttemptText(null)).toBe("");
  });
});

describe("backoffSeconds", () => {
  it("matches the orchestrator's 2**attempt", () => {
    // worker/orchestrator.py: `2**attempt + random()`. The jitter is why the UI says "about".
    expect([1, 2, 3].map(backoffSeconds)).toEqual([2, 4, 8]);
  });
});

describe("applyFilter", () => {
  // `social_post` is titled "Social Media" on purpose: an agent's type and its catalog title need
  // not share a word, and a seventh agent (AT-12) can be named anything at all.
  const rows = [
    row({ node_id: "a", agent_type: "researcher", status: "success", error_message: null }),
    row({ node_id: "b", agent_type: "social_post", status: "failed", error_message: "[attempt 1] Token revoked." }),
    row({ node_id: "c", agent_type: "email", status: "skipped", error_message: null }),
  ];
  const titleOf = (type: string) => ({ researcher: "Researcher", social_post: "Social Media", email: "Email" })[type] ?? type;

  it("matches the agent name a person can actually see, not just its type", () => {
    // "Social Media" is on the screen; "social_post" is in the data and shares no word with it.
    // Searching the type alone would find nothing.
    expect(applyFilter(rows, { text: "Media", statuses: [], agents: [] }, titleOf).map((r) => r.node_id)).toEqual(["b"]);
  });

  it("still matches the raw type, which is what an id in a bug report gives you", () => {
    expect(applyFilter(rows, { text: "social_post", statuses: [], agents: [] }, titleOf).map((r) => r.node_id)).toEqual(["b"]);
  });

  it("matches error text", () => {
    expect(applyFilter(rows, { text: "revoked", statuses: [], agents: [] }, titleOf).map((r) => r.node_id)).toEqual(["b"]);
  });

  it("keeps only the chosen status", () => {
    expect(applyFilter(rows, { text: "", statuses: ["skipped"], agents: [] }, titleOf).map((r) => r.node_id)).toEqual(["c"]);
  });

  it("combines status and text rather than choosing one", () => {
    expect(applyFilter(rows, { text: "revoked", statuses: ["success"], agents: [] }, titleOf)).toEqual([]);
  });

  it("returns everything when nothing is set", () => {
    expect(applyFilter(rows, { text: "  ", statuses: [], agents: [] }, titleOf)).toHaveLength(3);
  });
});

describe("toCsv", () => {
  it("writes the columns §21 S-07 names, in that order", () => {
    expect(toCsv([]).trim()).toBe(CSV_COLUMNS.join(","));
  });

  it("writes timestamps in UTC whatever the reader's zone", () => {
    // Deliberately given with an offset, not already in UTC: a fixture that is *already*
    // "…Z" would pass even if the value were copied through untouched.
    const csv = toCsv([row({ started_at: "2026-09-20T19:09:40+03:00", completed_at: null, duration_ms: null })]);
    const cells = csv.split("\n")[1]!.split(",");
    expect(cells[4]).toBe("2026-09-20T16:09:40.000Z");
    // Absent is empty, not "null" or "Invalid Date".
    expect(cells[5]).toBe("");
    expect(cells[6]).toBe("");
  });

  it("quotes a message containing commas, quotes and newlines so the row survives", () => {
    // Without this a multi-attempt error would break into several rows and shift every column.
    const csv = toCsv([row({ error_message: '[attempt 1] Bad "input", line 2\n[attempt 2] Gave up' })]);
    const body = csv.slice(csv.indexOf("\n") + 1);
    expect(body).toContain('"[attempt 1] Bad ""input"", line 2\n[attempt 2] Gave up"');
    // One record, even though the value spans two physical lines.
    expect(body.trimEnd().split("\n")).toHaveLength(2);
  });

  it("ends with a newline, so the last record is not truncated", () => {
    expect(toCsv([row()]).endsWith("\n")).toBe(true);
  });

  it("writes a retry count of zero rather than leaving it blank", () => {
    const cells = toCsv([row({ retry_count: 0 })]).split("\n")[1]!.split(",");
    expect(cells[7]).toBe("0");
  });
});

describe("retryLabel (§16.5)", () => {
  it("says how much rope is left, not just that it is trying again", () => {
    expect(retryLabel(1)).toBe("Retrying 1/3");
    expect(retryLabel(3)).toBe("Retrying 3/3");
  });

  it("never reads 0/3 or 4/3", () => {
    // The orchestrator increments before it writes `retrying`, so neither should arrive — but the
    // canvas node passes `data.retryCount ?? 0` unguarded, and nonsense on screen is worse than a
    // clamp. AgentNode.tsx and StepList.tsx both render this string.
    expect(retryLabel(0)).toBe("Retrying 1/3");
    expect(retryLabel(9)).toBe("Retrying 3/3");
  });
});

describe("retryWaitLabel", () => {
  it("names the retry and the wait the orchestrator takes before it", () => {
    expect(retryWaitLabel(1)).toBe("Retry 1 of 3, about 2s later.");
    expect(retryWaitLabel(2)).toBe("Retry 2 of 3, about 4s later.");
    expect(retryWaitLabel(3)).toBe("Retry 3 of 3, about 8s later.");
  });

  it("cannot claim a fourth retry out of three", () => {
    expect(retryWaitLabel(4)).toBe("Retry 3 of 3, about 8s later.");
  });
});
