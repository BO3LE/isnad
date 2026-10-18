import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultReview } from "./ResultReview";
import { ToastContext } from "@/design-system/components/toast-context";
import { endpoints, type AgentManifest, type NodeState, type OutputLink, type RunOutput, type StepResult } from "@/lib/api";
import catalog from "@/test/catalog.json";

// The review of a step's result: what it shows, and exactly what each choice sends.

const agents = catalog as unknown as AgentManifest[];

const step = (over: Partial<NodeState> = {}): NodeState => ({
  node_id: "w",
  agent_type: "writer",
  status: "awaiting_approval",
  retry_count: 0,
  revision: 0,
  started_at: null,
  completed_at: null,
  duration_ms: null,
  error_message: null,
  ...over,
});

const output = (over: Partial<RunOutput>): RunOutput => ({
  id: "o1",
  node_id: "w",
  agent_type: "writer",
  kind: "text",
  filename: null,
  mime_type: null,
  bytes: null,
  created_at: "2026-10-19T10:00:00Z",
  ...over,
});

const ARTICLE: StepResult = {
  node_id: "w",
  agent_type: "writer",
  revision: 0,
  editable: [
    { name: "title", title: "title", kind: "text", value: "Solar in Riyadh" },
    { name: "article_md", title: "article", kind: "text", value: "# Solar in Riyadh\n\nThe sun is strong." },
  ],
};

function show({
  node = step(),
  outputs = [output({ id: "text" })],
  links = { text: { id: "text", url: null, expires_in: 0, text: "title: Solar in Riyadh" } },
  result = ARTICLE,
  nextTitle = "Video" as string | null,
}: {
  node?: NodeState;
  outputs?: RunOutput[];
  links?: Record<string, OutputLink>;
  result?: StepResult;
  nextTitle?: string | null;
} = {}) {
  vi.spyOn(endpoints, "runOutputs").mockResolvedValue(outputs);
  vi.spyOn(endpoints, "output").mockImplementation(async (id: string) => links[id] ?? { id, url: null, expires_in: 0 });
  vi.spyOn(endpoints, "stepResult").mockResolvedValue(result);
  const approve = vi.spyOn(endpoints, "approve").mockResolvedValue({ run_id: "run-1", status: "queued" });
  const decided = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastContext.Provider value={vi.fn()}>
        <ResultReview runId="run-1" step={node} agents={agents} nextTitle={nextTitle} onDecided={decided} />
      </ToastContext.Provider>
    </QueryClientProvider>,
  );
  return { approve, decided };
}

afterEach(() => vi.restoreAllMocks());

describe("ResultReview", () => {
  it("shows the step's result and says what runs once it is approved", async () => {
    show();
    expect(screen.getByRole("heading", { name: "Writer's result" })).toBeInTheDocument();
    expect(await screen.findByText("title: Solar in Riyadh")).toBeInTheDocument();
    expect(screen.getByText(/Video runs only after you approve this/)).toBeInTheDocument();
  });

  it("approves the result as it is", async () => {
    const { approve, decided } = show();
    await userEvent.click(await screen.findByRole("button", { name: "Approve and run Video" }));
    expect(approve).toHaveBeenCalledWith("run-1", "w", "approve", undefined, undefined);
    expect(decided).toHaveBeenCalled();
  });

  it("approves the person's own version, sending only what they changed", async () => {
    const { approve } = show();
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const article = screen.getByLabelText("Article");
    await userEvent.clear(article);
    await userEvent.type(article, "My own words.");
    await userEvent.click(screen.getByRole("button", { name: "Approve my version and run Video" }));
    expect(approve).toHaveBeenCalledWith("run-1", "w", "approve", undefined, { article_md: "My own words." });
  });

  it("edits a list one line each, and drops blank lines", async () => {
    const { approve } = show({
      node: step({ node_id: "r", agent_type: "researcher" }),
      outputs: [output({ id: "text", node_id: "r", agent_type: "researcher" })],
      result: {
        node_id: "r",
        agent_type: "researcher",
        revision: 0,
        editable: [{ name: "notes", title: "notes", kind: "lines", value: ["One.", "Two."] }],
      },
      nextTitle: "Writer",
    });
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const notes = screen.getByLabelText("Notes");
    await userEvent.type(notes, "\n\nThree.");
    await userEvent.click(screen.getByRole("button", { name: "Approve my version and run Writer" }));
    expect(approve).toHaveBeenCalledWith("run-1", "r", "approve", undefined, { notes: ["One.", "Two.", "Three."] });
  });

  it("sends the result back with a note to be redone", async () => {
    const { approve } = show();
    await userEvent.click(await screen.findByRole("button", { name: "Redo with a note…" }));
    await userEvent.type(screen.getByLabelText("What should change?"), "Focus on costs.");
    await userEvent.click(screen.getByRole("button", { name: "Redo Writer" }));
    expect(approve).toHaveBeenCalledWith("run-1", "w", "redo", "Focus on costs.", undefined);
  });

  it("stops the run only with a reason, which is kept", async () => {
    const { approve } = show();
    await userEvent.click(await screen.findByRole("button", { name: "Stop the run…" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop the run" }));
    expect(approve).not.toHaveBeenCalled();
    expect(screen.getByText("Add a note — it's kept with the run.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Why are you stopping the run/), "Wrong topic.");
    await userEvent.click(screen.getByRole("button", { name: "Stop the run" }));
    expect(approve).toHaveBeenCalledWith("run-1", "w", "reject", "Wrong topic.", undefined);
  });

  it("names a redone result's version and what the person asked for", async () => {
    show({
      node: step({
        revision: 1,
        approval: { decision: "redo", note: "Focus on costs.", decided_at: "2026-10-19T10:00:00Z", revision: 0, edited: false },
      }),
    });
    expect(screen.getByText("version 2")).toBeInTheDocument();
    expect(screen.getByText(/You asked: “Focus on costs.”/)).toBeInTheDocument();
  });

  it("shows a video itself rather than where it is stored, and offers nothing to edit", async () => {
    show({
      node: step({ node_id: "v", agent_type: "video" }),
      outputs: [
        output({ id: "text", node_id: "v", agent_type: "video" }),
        output({ id: "file", node_id: "v", agent_type: "video", kind: "file", filename: "video.mp4", mime_type: "video/mp4" }),
      ],
      links: {
        text: { id: "text", url: null, expires_in: 0, text: "video: u/r/videos/ab/video.mp4" },
        file: { id: "file", url: "https://files.test/video.mp4", expires_in: 3600 },
      },
      result: { node_id: "v", agent_type: "video", revision: 0, editable: [] },
      nextTitle: null,
    });
    expect(await screen.findByLabelText("video.mp4")).toHaveAttribute("src", "https://files.test/video.mp4");
    expect(screen.queryByText(/u\/r\/videos/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve and finish" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });
});
