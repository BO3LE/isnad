import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Segmented } from "./Segmented";

function Harness() {
  const [value, setValue] = useState("short");
  return (
    <Segmented
      label="Length"
      value={value}
      onChange={setValue}
      options={[
        { value: "short", label: "Short" },
        { value: "medium", label: "Medium" },
        { value: "long", label: "Long" },
      ]}
    />
  );
}

describe("Segmented", () => {
  it("is one tab stop and moves with the arrow keys (§13)", async () => {
    render(<Harness />);
    const short = screen.getByRole("radio", { name: "Short" });
    const medium = screen.getByRole("radio", { name: "Medium" });

    expect(short).toHaveAttribute("tabindex", "0");
    expect(medium).toHaveAttribute("tabindex", "-1");

    await userEvent.tab();
    expect(short).toHaveFocus();

    await userEvent.keyboard("{ArrowRight}");
    expect(medium).toHaveAttribute("aria-checked", "true");
    expect(medium).toHaveFocus();
  });

  it("wraps around at the ends", async () => {
    render(<Harness />);
    await userEvent.tab();
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Long" })).toHaveAttribute("aria-checked", "true");
  });
});
