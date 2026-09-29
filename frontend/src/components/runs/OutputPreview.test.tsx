import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OutputPreview } from "./OutputPreview";
import { ApiError, endpoints, type AgentManifest, type OutputLink, type RunOutput } from "@/lib/api";
import catalog from "@/test/catalog.json";

// The branches the approval window renders. The e2e spec drives the article and the video; these
// cover the ones it cannot reach — an image, a published link, nothing at all, and a failed open.

const agents = catalog as unknown as AgentManifest[];

const output = (over: Partial<RunOutput>): RunOutput => ({
  id: "o1",
  node_id: "n1",
  agent_type: "video",
  kind: "file",
  filename: null,
  mime_type: null,
  bytes: null,
  created_at: "2026-09-20T10:00:00Z",
  ...over,
});

function show(outputs: RunOutput[], links: Record<string, OutputLink | Error> = {}) {
  vi.spyOn(endpoints, "runOutputs").mockResolvedValue(outputs);
  vi.spyOn(endpoints, "output").mockImplementation(async (id: string) => {
    const link = links[id];
    if (link instanceof Error) throw link;
    return link ?? { id, url: null, expires_in: 0, text: null };
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OutputPreview runId="run-1" agents={agents} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OutputPreview", () => {
  it("shows an image in place", async () => {
    show(
      [output({ id: "img", agent_type: "image", kind: "file", filename: "image-1.png", mime_type: "image/png" })],
      { img: { id: "img", url: "https://files.test/image-1.png", expires_in: 3600 } },
    );
    const image = await screen.findByRole("img", { name: "image-1.png" });
    expect(image).toHaveAttribute("src", "https://files.test/image-1.png");
  });

  it("offers a published link rather than trying to draw it", async () => {
    show([output({ id: "url", agent_type: "publisher", kind: "url" })], {
      url: { id: "url", url: "https://youtube.com/watch?v=abc", expires_in: 0 },
    });
    const link = await screen.findByRole("link", { name: "https://youtube.com/watch?v=abc" });
    expect(link).toHaveAttribute("href", "https://youtube.com/watch?v=abc");
    expect(screen.getByRole("tab", { name: "Publisher · link" })).toBeInTheDocument();
  });

  it("says plainly when a run has made nothing yet", async () => {
    show([]);
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("says so when one output will not open, without losing the others", async () => {
    show(
      [
        output({ id: "bad", agent_type: "researcher", kind: "text" }),
        output({ id: "good", agent_type: "writer", kind: "text" }),
      ],
      {
        bad: new ApiError(404, "This output has nothing in it."),
        good: { id: "good", url: null, expires_in: 0, text: "The article" },
      },
    );
    expect(await screen.findByText(/This output has nothing in it\./)).toBeInTheDocument();

    // The other tab still works, so one bad output does not take the window down.
    await userEvent.click(screen.getByRole("tab", { name: "Writer · text" }));
    expect(await screen.findByText("The article")).toBeInTheDocument();
  });

  it("names every tab from the catalog, so a seventh agent lists itself", async () => {
    show([
      output({ id: "a", agent_type: "writer", kind: "text" }),
      output({ id: "b", agent_type: "translator", kind: "file", filename: "ar.md", mime_type: "text/markdown" }),
    ]);
    expect(await screen.findByRole("tab", { name: "Writer · text" })).toBeInTheDocument();
    // Not in the catalog: it still lists, under the name the run recorded.
    expect(screen.getByRole("tab", { name: "translator · ar.md" })).toBeInTheDocument();
  });
});
