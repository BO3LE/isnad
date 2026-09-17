import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { TagInput } from "./TagInput";

function Harness({ initial = [] as string[] }) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <TagInput
        label="To"
        value={value}
        onChange={setValue}
        onError={setError}
        check={(item) => (item.includes("@") ? null : `“${item}” isn't an email address.`)}
        placeholder="Add an address"
      />
      <p data-testid="value">{value.join("|")}</p>
      {error && <p role="alert">{error}</p>}
    </>
  );
}

describe("TagInput", () => {
  it("adds on Enter and on comma", async () => {
    render(<Harness />);
    const input = screen.getByPlaceholderText("Add an address");
    await userEvent.type(input, "a@b.co{Enter}c@d.co,");
    expect(screen.getByTestId("value")).toHaveTextContent("a@b.co|c@d.co");
  });

  it("adds what was typed when the field loses focus", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByPlaceholderText("Add an address"), "a@b.co");
    await userEvent.tab();
    expect(screen.getByTestId("value")).toHaveTextContent("a@b.co");
  });

  it("refuses an item that fails the check and says why", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByPlaceholderText("Add an address"), "demo{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent("");
    expect(screen.getByRole("alert")).toHaveTextContent("“demo” isn't an email address.");
  });

  it("removes a chip with its button, or the last one with Backspace", async () => {
    render(<Harness initial={["a@b.co", "c@d.co", "e@f.co"]} />);
    await userEvent.click(screen.getByRole("button", { name: "Remove a@b.co" }));
    expect(screen.getByTestId("value")).toHaveTextContent("c@d.co|e@f.co");
    await userEvent.click(screen.getByRole("list", { name: "To" }).parentElement!);
    await userEvent.keyboard("{Backspace}");
    expect(screen.getByTestId("value")).toHaveTextContent("c@d.co");
  });

  it("does not add the same item twice", async () => {
    render(<Harness initial={["a@b.co"]} />);
    await userEvent.type(screen.getByRole("textbox"), "a@b.co{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent(/^a@b\.co$/);
  });
});
