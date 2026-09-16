import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { RegisterPage } from "./RegisterPage";

const register = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth-client")>()),
  register,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  );
}

describe("P-02 Create account", () => {
  beforeEach(() => register.mockReset());

  it("shows the password rule before the user types", () => {
    renderPage();
    expect(screen.getByText("At least 8 characters")).toBeInTheDocument();
  });

  it("does not submit a password that is too short, or one that does not match", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/Email/), "new@kfu.edu.sa");
    await userEvent.type(screen.getByLabelText(/^Password/), "short");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "different");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(register).not.toHaveBeenCalled();
    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(screen.getByText("Both passwords must match.")).toBeInTheDocument();
  });

  it("submits once the rules are met", async () => {
    register.mockResolvedValue({ access_token: "token", token_type: "bearer" });
    renderPage();
    await userEvent.type(screen.getByLabelText(/Email/), "new@kfu.edu.sa");
    await userEvent.type(screen.getByLabelText(/^Password/), "a-long-enough-password");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "a-long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(register).toHaveBeenCalledWith({ email: "new@kfu.edu.sa", password: "a-long-enough-password" });
  });

  it("reveals a password only on request, one field at a time", async () => {
    renderPage();
    const password = screen.getByLabelText(/^Password/);
    expect(password).toHaveAttribute("type", "password");

    await userEvent.click(screen.getAllByRole("button", { name: "Show password" })[0]!);
    expect(password).toHaveAttribute("type", "text");
    // The confirm field is untouched by the other field's toggle.
    expect(screen.getByLabelText(/Confirm password/)).toHaveAttribute("type", "password");
  });
});
