// Connecting a Google account (D-09) and saying where a connection stands (DESIGN-SYSTEM §17.3, S-09).
//
// The account is connected in a popup, so the canvas and any open drawer stay as they are. Google's
// sign-in pages send `Cross-Origin-Opener-Policy: same-origin`, which in Chrome cuts the popup off
// from this tab: `popup.closed` reads true while the person is still on Google's screen, and the
// callback can't `postMessage` back. So the callback returns the popup to Settings → Connections
// with `popup=1`, and that page — same origin as this tab — reports on a BroadcastChannel and closes
// itself. Where the opener survives, the callback's own postMessage is accepted too. A blocked popup
// becomes a full-page redirect that ends on the same Connections page.
//
// Google won't grant YouTube and Drive in one consent ("scopes that cannot be requested together"),
// so an account is connected once for YouTube and once for Drive and Gmail — two connections, each
// shown and chosen on its own (api/google_oauth.py).
import { API_URL, endpoints, type Connection, type ConnectionAccess } from "./api";

export type ConnectResult = { ok: true } | { ok: false; reason: "cancelled" | "denied" | "state" | "failed" | "redirecting" };
export interface ConnectMessage {
  type: typeof MESSAGE_TYPE;
  ok: boolean;
  error?: string | null;
}

export const SECURITY = "Tokens are stored encrypted and never appear in your workflows.";

/** The two things a Google account can be connected for, in the order they are offered. */
export const ACCESS: Record<ConnectionAccess, { label: string; does: string }> = {
  youtube: { label: "YouTube", does: "Upload videos to the account's YouTube channel, unlisted unless a step says otherwise." },
  drive_gmail: { label: "Drive and Gmail", does: "Save files to the account's Google Drive and send email as it." },
};
export const ACCESS_ORDER: ConnectionAccess[] = ["youtube", "drive_gmail"];

export const MESSAGE_TYPE = "isnad:google-connection";
export const CHANNEL = "isnad-google-connection";
const POPUP = "width=520,height=680";

/**
 * Open Google's consent screen for `access` and settle when it reports back — or when `signal`
 * aborts, which is how the person cancels (a closed popup can't be told apart from one on Google's
 * page; see above).
 *
 * Call it straight from a click: the window is opened before anything is awaited, which is what
 * keeps popup blockers from stopping it.
 */
export async function connectGoogle(access: ConnectionAccess, signal?: AbortSignal, win: Window = window): Promise<ConnectResult> {
  const popup = win.open("", "isnad-google", POPUP);
  if (!popup) {
    const { authorization_url } = await endpoints.startGoogle(access, "redirect");
    win.location.assign(authorization_url);
    return { ok: false, reason: "redirecting" };
  }
  let url: string;
  try {
    url = (await endpoints.startGoogle(access, "popup")).authorization_url;
  } catch (error) {
    popup.close();
    throw error;
  }
  popup.location.href = url;
  const apiOrigin = new URL(API_URL, win.location.href).origin;
  const channel = new BroadcastChannel(CHANNEL);

  return new Promise<ConnectResult>((resolve) => {
    const done = (result: ConnectResult) => {
      channel.close();
      win.removeEventListener("message", onMessage);
      signal?.removeEventListener("abort", onAbort);
      resolve(result);
    };
    const settle = (data: Partial<ConnectMessage> | undefined) => {
      if (data?.type !== MESSAGE_TYPE) return;
      if (data.ok) return done({ ok: true });
      done({ ok: false, reason: data.error === "denied" || data.error === "state" ? data.error : "failed" });
    };
    function onMessage(event: MessageEvent) {
      if (event.origin === apiOrigin) settle(event.data); // only the API's own callback page
    }
    function onAbort() {
      popup?.close();
      done({ ok: false, reason: "cancelled" });
    }
    channel.onmessage = (event: MessageEvent) => settle(event.data);
    win.addEventListener("message", onMessage);
    if (signal?.aborted) onAbort();
    else signal?.addEventListener("abort", onAbort);
  });
}

/** In the popup, back on Connections: tell the tab that is waiting, then close. */
export function reportToOpener(message: ConnectMessage, win: Window = window): void {
  const channel = new BroadcastChannel(CHANNEL);
  channel.postMessage(message);
  channel.close();
  win.close();
}

/** What a failed connection attempt tells the person; nothing for one they simply closed. */
export function connectProblem(reason: string | null | undefined): string | null {
  switch (reason) {
    case "denied":
    case "google_denied":
      return "Google wasn't connected: the permission screen was cancelled.";
    case "state":
    case "google_state":
      return "That sign-in link expired, was used twice or was opened in another browser. Try again.";
    case "failed":
    case "google_failed":
      return "Google didn't connect the account. Try again.";
    default:
      return null;
  }
}

const DAY = 24 * 60 * 60 * 1000;

function daysUntil(iso: string, now: Date): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY));
}

function inDays(days: number): string {
  if (days === 0) return "today";
  return days === 1 ? "in 1 day" : `in ${days} days`;
}

/** The status line under an account (§17.3): "Connected · expires in 58 days", "Expires in 3 days — Reconnect". */
export function connectionStatus(connection: Connection, now: Date = new Date()): { tone: "ok" | "warning" | "danger"; text: string } {
  if (connection.status === "expired") return { tone: "danger", text: "Connection expired — Reconnect" };
  const expires = connection.expires_at ? daysUntil(connection.expires_at, now) : null;
  if (connection.status === "expiring") {
    return { tone: "warning", text: expires === null ? "Expiring soon — Reconnect" : `Expires ${inDays(expires)} — Reconnect` };
  }
  return { tone: "ok", text: expires === null ? "Connected" : `Connected · expires ${inDays(expires)}` };
}

/** What a connection may do as a person reads it ("YouTube", "Drive · Gmail"). */
export function services(connection: Connection): string {
  return connection.scopes.length ? connection.scopes.join(" · ") : "Nothing allowed — reconnect and tick it on Google's screen";
}

/** A connection in the step's account picker: "team@example.org — YouTube". */
export function connectionLabel(connection: Connection): string {
  const label = `${connection.account_email} — ${services(connection)}`;
  return connection.status === "expired" ? `${label} (expired)` : label;
}

export interface GoogleAccount {
  email: string;
  connections: Connection[];
}

/** Connections grouped by Google account, in the order each account was first connected. */
export function byAccount(connections: Connection[]): GoogleAccount[] {
  const accounts = new Map<string, Connection[]>();
  for (const connection of connections) {
    accounts.set(connection.account_email, [...(accounts.get(connection.account_email) ?? []), connection]);
  }
  return [...accounts].map(([email, grouped]) => ({ email, connections: grouped }));
}

export function usedBy(count: number): string {
  if (count === 0) return "Not used by any workflow yet";
  return count === 1 ? "Used by 1 workflow" : `Used by ${count} workflows`;
}
