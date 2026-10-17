import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Tabs } from "./Tabs";
import { tabPanel } from "./tab-panel";

// §14.9 and §13 — a tab has to reach its panel. The pairing is two strings that must agree across
// two files, so these assert they actually line up rather than that each side looks plausible.

function Example({ label = "Step panels", idPrefix }: { label?: string; idPrefix?: string }) {
  const [tab, setTab] = useState("settings");
  return (
    <>
      <Tabs
        label={label}
        idPrefix={idPrefix}
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "settings", label: "Settings" },
          { id: "output", label: "Last output" },
        ]}
      />
      <div {...tabPanel(idPrefix ?? label, tab)}>{tab === "settings" ? "the form" : "what it made"}</div>
    </>
  );
}

describe("Tabs", () => {
  it("points each tab at the panel that answers it", async () => {
    render(<Example />);
    const settings = screen.getByRole("tab", { name: "Settings" });
    const panel = screen.getByRole("tabpanel");

    // The tab names the panel, and the panel names the tab back. Either alone is not the pattern.
    expect(settings).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", settings.id);
    expect(panel).toHaveAccessibleName("Settings");
  });

  it("follows the selection to the other panel", async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole("tab", { name: "Last output" }));

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveTextContent("what it made");
    expect(screen.getByRole("tab", { name: "Last output" })).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAccessibleName("Last output");
  });

  it("keeps two tablists on one page from claiming each other's panels", () => {
    // The drawer does exactly this: a step's panels, and inside one of them the outputs it made.
    render(
      <>
        <Example label="Step panels" />
        <Example label="What this step made" />
      </>,
    );
    const [outer, inner] = screen.getAllByRole("tabpanel");
    expect(outer!.id).not.toBe(inner!.id);
    expect(screen.getAllByRole("tab", { name: "Settings" }).map((t) => t.getAttribute("aria-controls"))).toEqual([
      outer!.id,
      inner!.id,
    ]);
  });

  it("takes an explicit prefix when two tablists would otherwise share a label", () => {
    render(
      <>
        <Example label="Outputs" idPrefix="run-outputs" />
        <Example label="Outputs" idPrefix="step-outputs" />
      </>,
    );
    const [first, second] = screen.getAllByRole("tabpanel");
    expect(first!.id).toBe("run-outputs-panel-settings");
    expect(second!.id).toBe("step-outputs-panel-settings");

    // The tabs must have followed the prefix too. Asserting only the panel ids would pass even if
    // the tablist ignored `idPrefix` entirely — both strips would then share one set of tab ids
    // and each would point at the other's panel.
    const tabs = screen.getAllByRole("tab", { name: "Settings" });
    expect(tabs.map((t) => t.id)).toEqual(["run-outputs-tab-settings", "step-outputs-tab-settings"]);
    expect(tabs.map((t) => t.getAttribute("aria-controls"))).toEqual([first!.id, second!.id]);
  });

  it("moves between tabs with the arrow keys (roving tabindex)", async () => {
    render(<Example />);
    const settings = screen.getByRole("tab", { name: "Settings" });
    settings.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Last output" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Last output" })).toHaveAttribute("aria-selected", "true");
  });

  it("is one tab stop, not one per tab", async () => {
    render(<Example />);
    // The unselected tab is reached with arrows, not Tab — otherwise a ten-tab strip is ten stops.
    expect(screen.getByRole("tab", { name: "Settings" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Last output" })).toHaveAttribute("tabindex", "-1");
  });
});
