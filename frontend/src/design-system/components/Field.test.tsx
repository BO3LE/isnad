import { render, screen } from "@testing-library/react";
import { Field } from "./Field";
import { Input } from "./Input";

describe("Field", () => {
  it("links the label, help text and control", () => {
    render(
      <Field label="Topic" help="What should the Researcher look into?">
        {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} />}
      </Field>,
    );
    const input = screen.getByLabelText("Topic");
    expect(input).toHaveAccessibleDescription("What should the Researcher look into?");
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("shows the error instead of the help text and marks the control invalid", () => {
    render(
      <Field label="Recipients" required help="Who gets the email?" error="Enter at least one recipient.">
        {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} />}
      </Field>,
    );
    const input = screen.getByLabelText(/Recipients/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter at least one recipient.");
    expect(screen.queryByText("Who gets the email?")).not.toBeInTheDocument();
  });

  // The error replaces the help text, so describing the control with both ids would leave
  // aria-describedby pointing at an element that was never rendered.
  it("only describes the control with ids that are in the document", () => {
    render(
      <Field label="Recipients" help="Who gets the email?" error="Enter at least one recipient.">
        {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} />}
      </Field>,
    );
    const ids = screen.getByLabelText("Recipients").getAttribute("aria-describedby")?.split(" ") ?? [];
    expect(ids).toHaveLength(1);
    ids.forEach((id) => expect(document.getElementById(id)).not.toBeNull());
  });
});
