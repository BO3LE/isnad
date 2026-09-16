import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Menu } from "./Menu";

describe("Menu", () => {
  const items = [
    { id: "open", label: "Open", onSelect: vi.fn() },
    { id: "delete", label: "Delete workflow", danger: true, separated: true, onSelect: vi.fn() },
  ];

  it("opens, moves with the arrow keys, and closes on Escape", async () => {
    render(<Menu items={items} trigger={(props) => <button {...props}>More</button>} />);
    const trigger = screen.getByRole("button", { name: "More" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menuitem", { name: "Open" })).toHaveFocus();

    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Delete workflow" })).toHaveFocus();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("runs the item's action and closes", async () => {
    render(<Menu items={items} trigger={(props) => <button {...props}>More</button>} />);
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Open" }));
    expect(items[0]?.onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
