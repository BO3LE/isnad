import { render, screen } from "@testing-library/react";
import { ValidationPanel } from "./ValidationPanel";
import type { ValidationResult } from "@/lib/api";

// These run React in development, where a duplicate key is a console.error. The Playwright specs
// cannot see that: they run against a production build, which strips the warning.

const noop = () => undefined;
const titleOf = () => "Video";

function show(result: ValidationResult) {
  render(<ValidationPanel result={result} titleOf={titleOf} onGoToStep={noop} onClose={noop} />);
}

describe("ValidationPanel", () => {
  it("keeps two issues of the same kind on the same step apart", () => {
    // api/services/validation.py emits one missing_config per unset required field, so this is
    // what a step with two required settings sends.
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    show({
      valid: false,
      issues: [
        { code: "missing_config", severity: "error", node_id: "v", message: "Video is missing narration voice." },
        { code: "missing_config", severity: "error", node_id: "v", message: "Video is missing resolution." },
      ],
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(error).not.toHaveBeenCalled();
    error.mockRestore();
  });

  it("renders the server's message exactly", () => {
    const message = "These steps form a loop: Writer → Video. Remove one connection.";
    show({ valid: false, issues: [{ code: "cycle_detected", severity: "error", node_id: "w", message }] });
    expect(screen.getByText(message, { exact: true })).toBeInTheDocument();
  });

  it("never calls a refusal ready, even when it lists no reasons", () => {
    show({ valid: false, issues: [] });
    expect(screen.getByRole("heading")).toHaveTextContent("This workflow can't run yet");
    expect(screen.queryByText("Ready to run")).not.toBeInTheDocument();
  });

  it("says a valid result carrying warnings is not a pass", () => {
    show({
      valid: true,
      issues: [{ code: "catalog_unavailable", severity: "warning", message: "Agent settings couldn't be checked." }],
    });
    expect(screen.getByRole("heading")).toHaveTextContent("1 warning");
  });

  it("offers no action for an issue the server did not attach to a step", () => {
    show({ valid: false, issues: [{ code: "empty_workflow", severity: "error", message: "Add at least one agent before running." }] });
    expect(screen.getByText("Add at least one agent before running.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Go to/ })).not.toBeInTheDocument();
  });

  it("offers no action for a step that is no longer on the canvas", () => {
    render(
      <ValidationPanel
        result={{ valid: false, issues: [{ code: "orphan_node", severity: "error", node_id: "gone", message: "Video isn't connected to anything." }] }}
        titleOf={() => null}
        onGoToStep={noop}
        onClose={noop}
      />,
    );
    expect(screen.queryByRole("button", { name: /^Go to/ })).not.toBeInTheDocument();
  });
});
