import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CredentialPicker } from "./CredentialPicker";
import { ToastProvider } from "@/design-system/components/Toast";
import { endpoints, type Connection } from "@/lib/api";
import type { FormField } from "@/lib/schema";

// §17.3: the step stores which account it acts as, by id — chosen from the user's connections.

const field: FormField = {
  key: "credential_id",
  title: "Google account",
  required: true,
  widget: "credential",
  options: [],
  hasDefault: false,
  provider: "google",
};

const connection = (over: Partial<Connection> = {}): Connection => ({
  id: "c1",
  provider: "google",
  account_email: "team@example.org",
  access: "youtube",
  scopes: ["YouTube"],
  status: "connected",
  expires_at: null,
  created_at: "2026-10-01T09:00:00Z",
  used_by: 0,
  ...over,
});

function picker(connections: Connection[], props: { value?: string; field?: FormField } = {}) {
  const fetched = vi.spyOn(endpoints, "connections").mockResolvedValue(connections);
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <MemoryRouter>
          <CredentialPicker field={props.field ?? field} value={props.value} onChange={onChange} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onChange, fetched };
}

afterEach(() => vi.restoreAllMocks());

it("stores the chosen connection's id, and nothing else", async () => {
  const { onChange } = picker([connection(), connection({ id: "c2", access: "drive_gmail", scopes: ["Drive", "Gmail"] })]);
  const user = userEvent.setup();

  // One account, two connections: each option says what it may do.
  await user.selectOptions(await screen.findByRole("combobox"), "team@example.org — Drive · Gmail");

  expect(onChange).toHaveBeenCalledWith("c2");
  expect(screen.getByRole("link", { name: "Manage connections" })).toHaveAttribute("href", "/settings/connections");
});

it("shows how the chosen account stands", async () => {
  picker([connection({ status: "expired" })], { value: "c1" });

  expect(await screen.findByText("Connection expired — Reconnect")).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "team@example.org — YouTube (expired)" })).toBeInTheDocument();
});

it("says so when the account the step used has been disconnected", async () => {
  picker([connection()], { value: "c-gone" });

  expect(await screen.findByText("The account this step used was disconnected. Choose another.")).toBeInTheDocument();
});

it("offers to connect Google when there is no account, asking which access first", async () => {
  picker([]);
  const user = userEvent.setup();

  expect(await screen.findByText("No Google account connected")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Connect Google" }));

  const dialog = screen.getByRole("dialog", { name: "Connect Google" });
  expect(within(dialog).getByRole("radio", { name: "YouTube" })).toBeChecked();
  expect(within(dialog).getByRole("radio", { name: "Drive and Gmail" })).not.toBeChecked();
});

it("asks for no account where this server doesn't use one", async () => {
  const { fetched } = picker([], { field: { ...field, connection: "unused" } });

  expect(screen.getByText("This server doesn't need an account for this step.")).toBeInTheDocument();
  expect(fetched).not.toHaveBeenCalled();
});
