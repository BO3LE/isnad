import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";
import { ToastProvider } from "./Toast";
import { useToast } from "./toast-context";

function Trigger({ variant, message }: { variant?: "success" | "error"; message: string }) {
  const toast = useToast();
  return <Button onClick={() => toast({ variant, message })}>Show</Button>;
}

describe("ToastProvider", () => {
  it("announces errors assertively and keeps them until dismissed", async () => {
    render(
      <ToastProvider>
        <Trigger variant="error" message="Couldn't save the workflow." />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Show" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't save the workflow.");

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uses role=status for non-errors", async () => {
    render(
      <ToastProvider>
        <Trigger variant="success" message="Run finished." />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Run finished.");
  });

  // A caller passing `variant: cond ? "error" : undefined` must still get the Info default
  // rather than an undefined icon lookup.
  it("falls back to info when variant is explicitly undefined", async () => {
    render(
      <ToastProvider>
        <Trigger variant={undefined} message="Saved." />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
  });
});
