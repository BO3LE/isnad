import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ToastProvider } from "@/design-system/components/Toast";
import { ConnectionsPage, ConnectionsRoute } from "./ConnectionsPage";
import { endpoints, type Connection } from "@/lib/api";
import { CHANNEL, MESSAGE_TYPE } from "@/lib/connections";

// P-10 / S-09: which accounts Isnad may act as, until when, what uses them — and never a token.

const connection = (over: Partial<Connection> = {}): Connection => ({
  id: "c1",
  provider: "google",
  account_email: "team@example.org",
  scopes: ["YouTube", "Drive", "Gmail"],
  status: "connected",
  expires_at: null,
  created_at: "2026-10-01T09:00:00Z",
  used_by: 2,
  ...over,
});

function show(connections: Connection[] | Error, url = "/settings/connections") {
  if (connections instanceof Error) vi.spyOn(endpoints, "connections").mockRejectedValue(connections);
  else vi.spyOn(endpoints, "connections").mockResolvedValue(connections);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/settings/connections" element={<ConnectionsRoute page={<ConnectionsPage />} />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ConnectionsPage", () => {
  it("shows each account with what it may do, its status and what uses it", async () => {
    show([connection(), connection({ id: "c2", account_email: "old@example.org", status: "expired", scopes: ["Gmail"], used_by: 0 })]);

    const list = await screen.findByRole("list", { name: "Connected accounts" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    const [first, second] = rows as [HTMLElement, HTMLElement];
    expect(within(first).getByText("team@example.org")).toBeInTheDocument();
    expect(within(first).getByText("YouTube · Drive · Gmail")).toBeInTheDocument();
    expect(within(first).getByText("Connected")).toBeInTheDocument();
    expect(within(first).getByText("Used by 2 workflows")).toBeInTheDocument();
    expect(within(second).getByText("Connection expired — Reconnect")).toBeInTheDocument();
    expect(within(second).getByText("Not used by any workflow yet")).toBeInTheDocument();
    expect(screen.getByText(/Tokens are stored encrypted/)).toBeInTheDocument();
  });

  it("offers to connect an account when there are none", async () => {
    show([]);

    expect(await screen.findByText("No connections yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Connect Google" })).toHaveLength(2); // header and empty state
  });

  it("explains what Google will be asked before sending anyone there", async () => {
    show([]);
    const user = userEvent.setup();

    const [inHeader] = await screen.findAllByRole("button", { name: "Connect Google" });
    await user.click(inHeader!);

    const dialog = screen.getByRole("dialog", { name: "Connect Google" });
    expect(within(dialog).getByText(/upload to YouTube, save to Drive and send email as you/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Continue to Google" })).toBeInTheDocument();
  });

  it("disconnects only after a confirmation that says what will break", async () => {
    show([connection()]);
    const disconnect = vi.spyOn(endpoints, "disconnect").mockResolvedValue(undefined);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Disconnect team@example.org" }));
    const dialog = screen.getByRole("dialog", { name: "Disconnect team@example.org?" });
    expect(within(dialog).getByText(/Used by 2 workflows\. Their steps .* will need another account/)).toBeInTheDocument();
    expect(disconnect).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(disconnect).toHaveBeenCalledWith("c1"));
    expect(await screen.findByText("Disconnected team@example.org.")).toBeInTheDocument();
  });

  it("says why, back from Google without a connection", async () => {
    show([], "/settings/connections?error=google_state");

    expect(await screen.findByText(/link expired, was used twice or was opened in another browser/)).toBeInTheDocument();
  });

  it("can't load: says so and offers to try again", async () => {
    show(new Error("down"));

    expect(await screen.findByText("Couldn't load your connections.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("in the connect popup, only tells the waiting tab how it went", async () => {
    const close = vi.spyOn(window, "close").mockImplementation(() => {});
    const heard = new Promise((resolve) => {
      const channel = new BroadcastChannel(CHANNEL);
      channel.onmessage = (event) => {
        channel.close();
        resolve(event.data);
      };
    });

    show([], "/settings/connections?connected=google&popup=1");

    await expect(heard).resolves.toEqual({ type: MESSAGE_TYPE, ok: true, error: null });
    expect(close).toHaveBeenCalled();
    expect(screen.getByText("Google connected. You can close this window.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Connections" })).toBeNull();
  });
});
