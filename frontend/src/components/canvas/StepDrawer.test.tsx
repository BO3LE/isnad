import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StepDrawer } from "./StepDrawer";
import { LastOutput } from "./LastOutput";
import type { LastOutputState } from "./useLastOutput";
import type { AgentNodeData } from "./AgentNode";
import type { StepHandover } from "@/lib/handover";
import { endpoints, type AgentManifest, type OutputLink, type RunOutput, type RunSummary } from "@/lib/api";
import catalog from "@/test/catalog.json";

// S-04's "Last output" tab (DESIGN-SYSTEM §17.6). What matters here is which outputs reach the tab
// and whether the tab is offered at all — the rendering itself is OutputPreview's, tested there.

const agents = catalog as unknown as AgentManifest[];
const writer = agents.find((a) => a.name === "writer")!;

const STEP = "node-writer";

const run = (over: Partial<RunSummary> = {}): RunSummary => ({
  id: "run-1",
  status: "succeeded",
  created_at: "2026-09-20T10:00:00Z",
  completed_at: "2026-09-20T10:05:00Z",
  reason: null,
  ...over,
});

const output = (over: Partial<RunOutput>): RunOutput => ({
  id: "o1",
  node_id: STEP,
  agent_type: "writer",
  kind: "text",
  filename: null,
  mime_type: null,
  bytes: null,
  created_at: "2026-09-20T10:00:00Z",
  ...over,
});

const handover: StepHandover = { sources: new Map(), needs: [], available: new Map() };

const data: AgentNodeData = {
  agentType: "writer",
  title: "Writer",
  icon: writer.icon,
  family: writer.family,
  step: 2,
  configuration: {},
  requiresApproval: false,
} as AgentNodeData;

function drawer(runs: RunSummary[], outputs: RunOutput[], links: Record<string, OutputLink> = {}) {
  vi.spyOn(endpoints, "workflowRuns").mockResolvedValue(runs);
  vi.spyOn(endpoints, "runOutputs").mockResolvedValue(outputs);
  vi.spyOn(endpoints, "output").mockImplementation(async (id: string) => links[id] ?? { id, url: null, expires_in: 0, text: null });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StepDrawer
        workflowId="wf-1"
        stepId={STEP}
        data={data}
        manifest={writer}
        catalog={agents}
        handover={handover}
        issues={[]}
        saveLabel=""
        userEmail={null}
        onConfigurationChange={() => undefined}
        onApprovalChange={() => undefined}
        onBeginEdit={() => undefined}
        onClose={() => undefined}
      />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => vi.restoreAllMocks());

describe("StepDrawer · Last output", () => {
  it("offers no second tab when the workflow has never run", async () => {
    const client = drawer([], []);
    expect(await screen.findByRole("tab", { name: "Settings" })).toBeInTheDocument();
    // Settled, not merely started: a spy records the call, not its answer, so wait for the data.
    await waitFor(() => expect(client.getQueryData(["workflow-runs", "wf-1"])).toEqual([]));
    expect(screen.queryByRole("tab", { name: "Last output" })).not.toBeInTheDocument();
  });

  it("shows this step's output and not another step's", async () => {
    drawer(
      [run()],
      // The other step's output comes first on purpose: with the filter gone it becomes
      // `outputs[0]` and is what renders, so all three assertions below fail rather than one.
      [output({ id: "theirs", node_id: "node-researcher", agent_type: "researcher" }), output({ id: "mine", node_id: STEP })],
      {
        mine: { id: "mine", url: null, expires_in: 0, text: "What the Writer wrote." },
        theirs: { id: "theirs", url: null, expires_in: 0, text: "What the Researcher found." },
      },
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Last output" }));
    expect(await screen.findByText("What the Writer wrote.")).toBeInTheDocument();
    expect(screen.queryByText("What the Researcher found.")).not.toBeInTheDocument();
    // The whole tab list, not a substring of it: an unfiltered panel would hold two outputs and so
    // would grow a second row of tabs. Only the drawer's own two may be here.
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Settings", "Last output"]);
  });

  it("offers no second tab when the last run produced nothing for this step", async () => {
    const client = drawer([run()], [output({ id: "theirs", node_id: "node-researcher", agent_type: "researcher" })]);
    expect(await screen.findByRole("tab", { name: "Settings" })).toBeInTheDocument();
    // The outputs have arrived and none of them is this step's — not "they have not arrived yet".
    await waitFor(() => expect(client.getQueryData(["run-outputs", "run-1"])).toHaveLength(1));
    expect(screen.queryByRole("tab", { name: "Last output" })).not.toBeInTheDocument();
  });

  it("asks only the first run the list returns, which the API orders newest first", async () => {
    // The hook takes runs[0] and does not sort. Newest-first is the API's guarantee
    // (api/src/api/routers/workflows.py — `.order_by(ExecutionRun.created_at.desc())`), so this
    // asserts the half that lives here: one run is asked about, and it is the first.
    drawer([run({ id: "first" }), run({ id: "second", created_at: "2026-09-19T10:00:00Z" })], [output({ id: "mine" })]);
    await screen.findByRole("tab", { name: "Last output" });
    expect(endpoints.runOutputs).toHaveBeenCalledWith("first");
    expect(endpoints.runOutputs).not.toHaveBeenCalledWith("second");
  });

  it("names each one when a step made several, and only then", async () => {
    drawer([run()], [output({ id: "mine" }), output({ id: "also", kind: "file", filename: "draft.pdf", mime_type: "application/pdf" })], {
      mine: { id: "mine", url: null, expires_in: 0, text: "What the Writer wrote." },
    });
    await userEvent.click(await screen.findByRole("tab", { name: "Last output" }));
    expect(await screen.findByRole("tab", { name: "draft.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Text" })).toBeInTheDocument();
  });

  it("keeps the preview on screen when a later refresh fails", async () => {
    // The integration half of the same rule LastOutput is unit-tested for. The assertion waits on
    // the DOM, not on refetchQueries' promise: awaiting the promise returns before the observer
    // notification reaches React, and reading the DOM there sees the frame before the error.
    const client = drawer([run()], [output({ id: "mine" })], {
      mine: { id: "mine", url: null, expires_in: 0, text: "What the Writer wrote." },
    });
    await userEvent.click(await screen.findByRole("tab", { name: "Last output" }));
    expect(await screen.findByText("What the Writer wrote.")).toBeInTheDocument();

    vi.mocked(endpoints.runOutputs).mockRejectedValue(new Error("network"));
    await client.refetchQueries({ queryKey: ["run-outputs", "run-1"] });
    await waitFor(() => expect(client.getQueryState(["run-outputs", "run-1"])?.status).toBe("error"));

    expect(screen.getByText("What the Writer wrote.")).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load what this step made/)).not.toBeInTheDocument();
  });

  it("shows no inner tabs when the step made exactly one thing", async () => {
    drawer([run()], [output({ id: "mine" })], { mine: { id: "mine", url: null, expires_in: 0, text: "Only this." } });
    await userEvent.click(await screen.findByRole("tab", { name: "Last output" }));
    expect(await screen.findByText("Only this.")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Text" })).not.toBeInTheDocument();
  });
});

// LastOutput is a pure function of the hook's result, so these drive it directly: the states below
// are the ones React Query really produces, and reaching them through the drawer depends on refetch
// timing that a test cannot pin down.
describe("LastOutput", () => {
  const state = (over: Partial<LastOutputState>): LastOutputState => ({
    outputs: [],
    ranAt: null,
    isPending: false,
    isError: false,
    ...over,
  });

  function show(s: LastOutputState, text = "What the Writer wrote.") {
    vi.spyOn(endpoints, "output").mockResolvedValue({ id: "mine", url: null, expires_in: 0, text });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LastOutput state={s} />
      </QueryClientProvider>,
    );
  }

  it("keeps the preview when a refresh fails behind it", async () => {
    // React Query holds the last good data through a failed refetch and reports both at once. The
    // drawer refetches on every open, so this pairing is routine, not exotic.
    show(state({ outputs: [output({ id: "mine" })], ranAt: "2026-09-20T10:00:00Z", isError: true }));
    expect(await screen.findByText("What the Writer wrote.")).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load what this step made/)).not.toBeInTheDocument();
  });

  it("calls a file a file even when nothing named it", () => {
    // The API derives a filename from the storage path; with no path there is no name, and the
    // label used to fall through to "Text" for something that is not text.
    show(
      state({
        outputs: [
          output({ id: "mine", kind: "file", filename: null, mime_type: "application/pdf" }),
          output({ id: "words", kind: "text" }),
        ],
      }),
    );
    expect(screen.getByRole("tab", { name: "File" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Text" })).toBeInTheDocument();
  });

  it("names the run's time without a dangling sentence, however old it is", () => {
    // Past a week formatRelativeTime returns an absolute date rather than "3h ago" (lib/format.ts).
    show(state({ outputs: [output({ id: "mine" })], ranAt: "2026-09-01T16:05:00Z" }));
    // The <time> element splits the sentence, so match the whole paragraph's text.
    // The <time> element splits the sentence, so read the whole paragraph. Month name and clock
    // are the runner's locale and zone, so assert the shape rather than an exact string.
    const line = [...document.querySelectorAll("p")].find((p) => p.textContent?.startsWith("From the last run"));
    expect(line?.textContent).toMatch(/^From the last run, .*2026.*\.$/);
    expect(line?.textContent).not.toMatch(/,\s*\.$/);
  });

  it("drops the line entirely when the run has no usable time", () => {
    show(state({ outputs: [output({ id: "mine" })], ranAt: "not-a-date" }));
    expect(screen.queryByText(/From the last run/)).not.toBeInTheDocument();
  });

  it("says so when there is nothing to fall back on", () => {
    show(state({ isError: true }));
    expect(screen.getByText(/Couldn't load what this step made/)).toBeInTheDocument();
  });

  it("waits quietly while the first fetch is still out", () => {
    show(state({ isPending: true }));
    expect(document.querySelector("[aria-busy]")).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load what this step made/)).not.toBeInTheDocument();
  });
});
