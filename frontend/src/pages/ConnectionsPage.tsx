import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Plus, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AppShell, PageBody, PageHeader } from "@/components/app/AppShell";
import { ConnectGoogleDialog } from "@/components/connections/ConnectGoogleDialog";
import { GoogleLogo } from "@/components/connections/GoogleLogo";
import { CONNECTIONS_KEY, useConnectGoogle } from "@/components/connections/useConnectGoogle";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { ConfirmDialog } from "@/design-system/components/Dialog";
import { EmptyState } from "@/design-system/components/EmptyState";
import { Skeleton } from "@/design-system/components/Skeleton";
import { useToast } from "@/design-system/components/toast-context";
import { endpoints, type Connection, type ConnectionAccess } from "@/lib/api";
import {
  ACCESS,
  ACCESS_ORDER,
  byAccount,
  connectProblem,
  connectionStatus,
  MESSAGE_TYPE,
  reportToOpener,
  SECURITY,
  services,
  usedBy,
  type GoogleAccount,
} from "@/lib/connections";

// P-10 (DESIGN-SYSTEM §21 S-09) — the Google accounts Isnad may publish and send email as (D-09).
// The page shows what a person needs to trust a connection — which account, what it may do, until
// when, and what uses it — and never a token. Google grants YouTube apart from Drive and Gmail, so
// each account lists both, connected or not.

/**
 * The route. Opened inside the connect popup (`popup=1`, see lib/connections.ts), it only reports
 * the result to the tab that is waiting and closes; otherwise it is the Connections page.
 */
export function ConnectionsRoute({ page }: { page: ReactNode }) {
  const [params] = useSearchParams();
  const popup = params.get("popup") === "1";
  const ok = params.get("connected") === "google";
  const error = params.get("error")?.replace(/^google_/, "") ?? null;
  const reported = useRef(false);

  useEffect(() => {
    if (!popup || reported.current) return;
    reported.current = true;
    reportToOpener({ type: MESSAGE_TYPE, ok, error });
  }, [popup, ok, error]);

  if (!popup) return <>{page}</>;
  return (
    <main className="grid min-h-screen place-items-center p-8 text-center">
      <p className="text-body-md text-text">
        {ok ? "Google connected. You can close this window." : "Google wasn't connected. You can close this window and try again."}
      </p>
    </main>
  );
}

export function ConnectionsPage() {
  const client = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [asking, setAsking] = useState<ConnectionAccess | null>(null);
  const [leaving, setLeaving] = useState<GoogleAccount | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const { connect, cancel, waiting } = useConnectGoogle();

  const connections = useQuery({ queryKey: CONNECTIONS_KEY, queryFn: endpoints.connections });

  // Back from a full-page redirect (a blocked popup): say how it went once, then tidy the URL.
  useEffect(() => {
    const connected = params.get("connected");
    const error = params.get("error");
    if (!connected && !error) return;
    if (connected === "google") toast({ variant: "success", message: "Google connected." });
    setProblem(connectProblem(error));
    setParams({}, { replace: true });
  }, [params, setParams, toast]);

  // The API forgets every connection of the account (Google may end them together).
  const disconnect = useMutation({
    mutationFn: (account: GoogleAccount) => endpoints.disconnect(account.connections[0]!.id),
    onSuccess: (_, account) => {
      toast({ message: `Disconnected ${account.email}.` });
      setLeaving(null);
      void client.invalidateQueries({ queryKey: CONNECTIONS_KEY });
    },
    onError: () => toast({ variant: "error", message: "Couldn't disconnect the account. Try again." }),
  });

  const start = (access: ConnectionAccess) => {
    setAsking(null);
    setProblem(null);
    void connect(access);
  };
  const connectButton = (
    <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => setAsking("youtube")} disabled={waiting}>
      Connect Google
    </Button>
  );
  const leavingUsedBy = leaving ? leaving.connections.reduce((sum, c) => sum + c.used_by, 0) : 0;

  return (
    <AppShell crumbs={[{ label: "Connections" }]}>
      <PageBody width="narrow">
        <PageHeader
          title="Connections"
          description="Accounts Isnad can use to publish and send email. We never show your password or tokens."
          actions={connectButton}
        />

        {waiting && (
          <Banner
            variant="info"
            action={
              <Button size="sm" onClick={cancel}>
                Cancel
              </Button>
            }
          >
            Waiting for Google — finish in the window that opened.
          </Banner>
        )}
        {problem && <Banner variant="error">{problem}</Banner>}

        {connections.isPending ? (
          <div className="grid gap-3" aria-busy="true" aria-label="Loading your connections">
            {[0, 1].map((i) => (
              <div key={i} className="grid gap-2 rounded-md border border-border bg-surface p-4">
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            ))}
          </div>
        ) : connections.isError ? (
          <Banner
            variant="error"
            action={
              <Button size="sm" onClick={() => void connections.refetch()}>
                Try again
              </Button>
            }
          >
            Couldn't load your connections.
          </Banner>
        ) : connections.data.length === 0 ? (
          <EmptyState
            title="No connections yet"
            body="Connect a Google account to publish to YouTube and Drive and to send email."
            actions={connectButton}
          />
        ) : (
          <ul className="grid gap-3" aria-label="Connected accounts">
            {byAccount(connections.data).map((account) => (
              <AccountCard
                key={account.email}
                account={account}
                busy={waiting}
                onConnect={setAsking}
                onDisconnect={() => setLeaving(account)}
              />
            ))}
          </ul>
        )}

        <p className="flex items-center gap-2 text-body-sm text-text-muted">
          <ShieldCheck size={16} aria-hidden />
          {SECURITY}
        </p>
      </PageBody>

      <ConnectGoogleDialog initial={asking} onClose={() => setAsking(null)} onContinue={start} />

      <ConfirmDialog
        open={leaving !== null}
        onClose={() => setLeaving(null)}
        onConfirm={() => leaving && disconnect.mutate(leaving)}
        loading={disconnect.isPending}
        title={leaving ? `Disconnect ${leaving.email}?` : "Disconnect"}
        description={
          leavingUsedBy > 0
            ? `${usedBy(leavingUsedBy)}. Their steps that publish or send as this account will need another account before they can run.`
            : "Isnad will forget this account's YouTube, Drive and Gmail access and ask Google to revoke it."
        }
        confirmLabel="Disconnect"
      />
    </AppShell>
  );
}

const TONE = {
  ok: { icon: CircleCheck, className: "text-status-success-fg" },
  warning: { icon: TriangleAlert, className: "text-status-retrying-fg" },
  danger: { icon: CircleX, className: "text-status-failed-fg" },
} as const;

function AccountCard({
  account,
  busy,
  onConnect,
  onDisconnect,
}: {
  account: GoogleAccount;
  busy: boolean;
  onConnect: (access: ConnectionAccess) => void;
  onDisconnect: () => void;
}) {
  // YouTube, then Drive and Gmail — each connected or not — then any connection from before the split.
  const lines = [
    ...ACCESS_ORDER.map((access) => ({ access, connection: account.connections.find((c) => c.access === access) })),
    ...account.connections.filter((c) => c.access === "all").map((connection) => ({ access: "youtube" as const, connection })),
  ];
  return (
    <li className="grid gap-3 rounded-md border border-border bg-surface p-4 shadow-1">
      <div className="flex items-center gap-3">
        <GoogleLogo size={24} />
        <p className="min-w-0 flex-1 truncate text-body-md font-medium text-text">{account.email}</p>
        <Button size="sm" variant="dangerSecondary" onClick={onDisconnect} aria-label={`Disconnect ${account.email}`}>
          Disconnect
        </Button>
      </div>
      <ul className="grid gap-2" aria-label={`What ${account.email} may do`}>
        {lines.map(({ access, connection }) => (
          <AccessLine
            key={connection?.id ?? access}
            email={account.email}
            access={access}
            connection={connection}
            busy={busy}
            onConnect={() => onConnect(access)}
          />
        ))}
      </ul>
    </li>
  );
}

function AccessLine({
  email,
  access,
  connection,
  busy,
  onConnect,
}: {
  email: string;
  access: ConnectionAccess;
  connection: Connection | undefined;
  busy: boolean;
  onConnect: () => void;
}) {
  const name = ACCESS[access].label;
  if (!connection) {
    return (
      <li className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-border p-3">
        <div className="grid gap-0.5">
          <p className="text-body-sm font-medium text-text">{name}</p>
          <p className="text-body-sm text-text-muted">Not connected</p>
        </div>
        <Button size="sm" onClick={onConnect} disabled={busy} aria-label={`Connect ${name} for ${email}`}>
          Connect
        </Button>
      </li>
    );
  }
  const status = connectionStatus(connection);
  const { icon: Icon, className } = TONE[status.tone];
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-border p-3">
      <div className="grid min-w-0 gap-0.5">
        <p className="text-body-sm font-medium text-text">{services(connection)}</p>
        <p className={`flex items-center gap-1.5 text-body-sm ${className}`}>
          <Icon size={14} aria-hidden />
          {status.text}
        </p>
        <p className="text-body-sm text-text-muted">{usedBy(connection.used_by)}</p>
      </div>
      <Button size="sm" onClick={onConnect} disabled={busy} aria-label={`Reconnect ${name} for ${email}`}>
        Reconnect
      </Button>
    </li>
  );
}
