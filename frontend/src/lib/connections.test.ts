import { endpoints, type Connection } from "./api";
import { CHANNEL, connectGoogle, connectProblem, connectionStatus, MESSAGE_TYPE, reportToOpener, usedBy } from "./connections";

const NOW = new Date("2026-10-17T12:00:00Z");
const connection = (over: Partial<Connection> = {}): Connection => ({
  id: "c1",
  provider: "google",
  account_email: "team@example.org",
  scopes: ["YouTube", "Drive", "Gmail"],
  status: "connected",
  expires_at: null,
  created_at: "2026-10-01T09:00:00Z",
  used_by: 0,
  ...over,
});

describe("connectionStatus (§17.3)", () => {
  it("says until when a connection lasts", () => {
    expect(connectionStatus(connection({ expires_at: "2026-12-14T12:00:00Z" }), NOW)).toEqual({
      tone: "ok",
      text: "Connected · expires in 58 days",
    });
    expect(connectionStatus(connection(), NOW)).toEqual({ tone: "ok", text: "Connected" });
  });

  it("warns before it runs out and asks for a reconnect once it has", () => {
    expect(connectionStatus(connection({ status: "expiring", expires_at: "2026-10-20T12:00:00Z" }), NOW)).toEqual({
      tone: "warning",
      text: "Expires in 3 days — Reconnect",
    });
    expect(connectionStatus(connection({ status: "expiring", expires_at: "2026-10-18T11:00:00Z" }), NOW).text).toBe(
      "Expires in 1 day — Reconnect",
    );
    expect(connectionStatus(connection({ status: "expired" }), NOW)).toEqual({ tone: "danger", text: "Connection expired — Reconnect" });
  });
});

it("counts the workflows that use a connection", () => {
  expect(usedBy(0)).toBe("Not used by any workflow yet");
  expect(usedBy(1)).toBe("Used by 1 workflow");
  expect(usedBy(3)).toBe("Used by 3 workflows");
});

it("explains a failed connection, and says nothing about one that was simply closed", () => {
  expect(connectProblem("google_denied")).toMatch(/cancelled/);
  expect(connectProblem("state")).toMatch(/another browser/);
  expect(connectProblem("failed")).toMatch(/Try again/);
  expect(connectProblem("cancelled")).toBeNull();
  expect(connectProblem(null)).toBeNull();
});

describe("connectGoogle", () => {
  const API = "http://localhost:8000";

  function fakeWindow(popup: { location: { href: string }; close: () => void; closed?: boolean } | null) {
    const events = new EventTarget();
    return Object.assign(events, {
      open: vi.fn(() => popup),
      location: { href: "http://localhost:5173/workflows/w1", assign: vi.fn() },
    }) as unknown as Window & { open: ReturnType<typeof vi.fn>; location: { assign: ReturnType<typeof vi.fn> } };
  }
  const popup = () => ({ location: { href: "" }, close: vi.fn(), closed: false });
  const tell = (data: unknown) => {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage(data);
    channel.close();
  };

  afterEach(() => vi.restoreAllMocks());

  it("opens the window before asking the API, then sends it to Google", async () => {
    const start = vi.spyOn(endpoints, "startGoogle").mockResolvedValue({ authorization_url: "https://accounts.google.test/o" });
    const window_ = popup();
    const win = fakeWindow(window_);

    const pending = connectGoogle(undefined, win);
    expect(win.open).toHaveBeenCalledTimes(1); // synchronously, inside the click
    await vi.waitFor(() => expect(window_.location.href).toBe("https://accounts.google.test/o"));
    expect(start).toHaveBeenCalledWith("popup");

    tell({ type: MESSAGE_TYPE, ok: true });
    await expect(pending).resolves.toEqual({ ok: true });
  });

  it("hears the app's page in the popup over a BroadcastChannel, even cut off from its opener", async () => {
    vi.spyOn(endpoints, "startGoogle").mockResolvedValue({ authorization_url: "https://accounts.google.test/o" });
    const window_ = popup();
    window_.closed = true; // what Chrome reports once Google's COOP has cut the popup off
    const pending = connectGoogle(undefined, fakeWindow(window_));
    await vi.waitFor(() => expect(window_.location.href).not.toBe(""));

    tell({ type: MESSAGE_TYPE, ok: false, error: "denied" });
    await expect(pending).resolves.toEqual({ ok: false, reason: "denied" });
  });

  it("accepts the callback's postMessage only from the API's origin", async () => {
    vi.spyOn(endpoints, "startGoogle").mockResolvedValue({ authorization_url: "https://accounts.google.test/o" });
    const window_ = popup();
    const win = fakeWindow(window_);
    const pending = connectGoogle(undefined, win);
    await vi.waitFor(() => expect(window_.location.href).not.toBe(""));
    let settled = false;
    void pending.then(() => (settled = true));

    win.dispatchEvent(new MessageEvent("message", { origin: "https://evil.test", data: { type: MESSAGE_TYPE, ok: true } }));
    await new Promise((r) => setTimeout(r, 20));
    expect(settled).toBe(false);

    win.dispatchEvent(new MessageEvent("message", { origin: API, data: { type: MESSAGE_TYPE, ok: true } }));
    await expect(pending).resolves.toEqual({ ok: true });
  });

  it("stops waiting and closes the popup when the person cancels", async () => {
    vi.spyOn(endpoints, "startGoogle").mockResolvedValue({ authorization_url: "https://accounts.google.test/o" });
    const window_ = popup();
    const controller = new AbortController();
    const pending = connectGoogle(controller.signal, fakeWindow(window_));
    await vi.waitFor(() => expect(window_.location.href).not.toBe(""));

    controller.abort();
    await expect(pending).resolves.toEqual({ ok: false, reason: "cancelled" });
    expect(window_.close).toHaveBeenCalled();
  });

  it("goes to Google in this tab when the popup is blocked", async () => {
    const start = vi.spyOn(endpoints, "startGoogle").mockResolvedValue({ authorization_url: "https://accounts.google.test/r" });
    const win = fakeWindow(null);

    await expect(connectGoogle(undefined, win)).resolves.toEqual({ ok: false, reason: "redirecting" });
    expect(start).toHaveBeenCalledWith("redirect");
    expect(win.location.assign).toHaveBeenCalledWith("https://accounts.google.test/r");
  });

  it("closes the popup and passes the error on when the API won't start (503: not set up)", async () => {
    vi.spyOn(endpoints, "startGoogle").mockRejectedValue(new Error("not set up"));
    const window_ = popup();

    await expect(connectGoogle(undefined, fakeWindow(window_))).rejects.toThrow("not set up");
    expect(window_.close).toHaveBeenCalled();
  });
});

it("in the popup, reports to the waiting tab and closes", async () => {
  const heard = new Promise((resolve) => {
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (event) => {
      channel.close();
      resolve(event.data);
    };
  });
  const win = { close: vi.fn() } as unknown as Window;

  reportToOpener({ type: MESSAGE_TYPE, ok: true, error: null }, win);

  await expect(heard).resolves.toEqual({ type: MESSAGE_TYPE, ok: true, error: null });
  expect(win.close).toHaveBeenCalled();
});
