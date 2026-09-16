import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "@/design-system/components/Toast";
import { WorkflowsPage } from "./WorkflowsPage";
import type { WorkflowSummary } from "@/lib/api";

const workflows = vi.hoisted(() => vi.fn());
const deleteWorkflow = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  endpoints: { workflows, deleteWorkflow, createWorkflow: vi.fn(), renameWorkflow: vi.fn() },
  duplicateWorkflow: vi.fn(),
}));

const summary = (over: Partial<WorkflowSummary> & { id: string; name: string }): WorkflowSummary =>
  ({
    status: "draft",
    agent_types: ["researcher", "writer"],
    updated_at: "2026-09-16T10:00:00Z",
    last_run: null,
    ...over,
  }) as WorkflowSummary;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <WorkflowsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("P-03 Workflows", () => {
  beforeEach(() => {
    workflows.mockReset();
    deleteWorkflow.mockReset();
  });

  it("invites the user to build a chain when they have none", async () => {
    workflows.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("Build your first chain")).toBeInTheDocument();
    // The toolbar would have nothing to act on and crowds the empty state.
    expect(screen.queryByLabelText("Search workflows")).not.toBeInTheDocument();
  });

  it("lists workflows with their step count and last run", async () => {
    workflows.mockResolvedValue([
      summary({ id: "1", name: "Weekly tech digest", last_run: { id: "r1", status: "succeeded", created_at: "2026-09-16T09:00:00Z", completed_at: "2026-09-16T09:05:00Z" } }),
    ]);
    renderPage();
    expect(await screen.findByText("Weekly tech digest")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByText("2 steps")).toBeInTheDocument();
  });

  it("filters by name, and offers a way out when nothing matches", async () => {
    workflows.mockResolvedValue([summary({ id: "1", name: "Weekly tech digest" }), summary({ id: "2", name: "Solar explainer" })]);
    renderPage();
    await screen.findByText("Weekly tech digest");

    await userEvent.type(screen.getByLabelText("Search workflows"), "solar");
    expect(screen.queryByText("Weekly tech digest")).not.toBeInTheDocument();
    expect(screen.getByText("Solar explainer")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Search workflows"));
    await userEvent.type(screen.getByLabelText("Search workflows"), "zzzz");
    expect(screen.getByText(/No workflows match/)).toBeInTheDocument();

    // Two controls clear the search: the ✕ inside the field, and the empty state's button that
    // S-02 asks for. The empty state renders last, so it is the second one.
    const clears = screen.getAllByRole("button", { name: "Clear search" });
    expect(clears).toHaveLength(2);
    await userEvent.click(clears[clears.length - 1]!);
    expect(screen.getByText("Weekly tech digest")).toBeInTheDocument();
  });

  // §14.12: a delete names the object and the consequence, and never happens on one click.
  it("does not delete until the confirm dialog is accepted", async () => {
    workflows.mockResolvedValue([summary({ id: "1", name: "Weekly tech digest" })]);
    deleteWorkflow.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("Weekly tech digest");

    await userEvent.click(screen.getByRole("button", { name: "Actions for Weekly tech digest" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Delete “Weekly tech digest”\?/)).toBeInTheDocument();
    expect(deleteWorkflow).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Delete workflow" }));
    await waitFor(() => expect(deleteWorkflow).toHaveBeenCalledWith("1"));
  });

  it("shows a retryable error rather than an empty page when the list fails", async () => {
    workflows.mockRejectedValue(new Error("Network is down."));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't load your workflows/);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
