import { render, screen } from "@testing-library/react";
import { StatusChip } from "./StatusChip";
import { nodeStatusMeta, runStatusMeta } from "./statusMeta";

describe("StatusChip", () => {
  it("shows a text label, not color alone", () => {
    render(<StatusChip meta={nodeStatusMeta.awaiting_approval} />);
    expect(screen.getByText("Needs approval")).toBeInTheDocument();
  });

  it("uses the status tone classes", () => {
    render(<StatusChip meta={nodeStatusMeta.failed} />);
    expect(screen.getByText("Failed")).toHaveClass("bg-status-failed-bg", "text-status-failed-fg");
  });

  it("covers every run status", () => {
    expect(Object.keys(runStatusMeta).sort()).toEqual(
      ["awaiting_approval", "cancelled", "failed", "queued", "running", "succeeded"].sort(),
    );
  });
});
