import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Plus, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AppShell, PageBody, PageHeader } from "@/components/app/AppShell";
import { GoogleLogo } from "@/components/connections/GoogleLogo";
import { CONNECTIONS_KEY, useConnectGoogle } from "@/components/connections/useConnectGoogle";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { ConfirmDialog, Dialog } from "@/design-system/components/Dialog";
import { EmptyState } from "@/design-system/components/EmptyState";
import { Skeleton } from "@/design-system/components/Skeleton";
import { useToast } from "@/design-system/components/toast-context";
import { endpoints, type Connection } from "@/lib/api";
import { connectProblem, connectionStatus, MESSAGE_TYPE, reportToOpener, usedBy } from "@/lib/connections";

// P-10 (DESIGN-SYSTEM §21 S-09) — the Google accounts Isnad may publish and send email as (D-09).
// The page shows what a person needs to trust a connection — which account, what it may do, until
// when, and what uses it — and never a token.

const SECURITY = "Tokens are stored encrypted and never appear in your workflows.";
const EXPLAIN = "Isnad will ask Google for permission to upload to YouTube, save to Drive and send email as you.";

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
  const [explaining, setExplaining] = useState(false);
  const [leaving, setLeaving] = useState<Connection | null>(null);
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

  const disconnect = useMutation({
    mutationFn: (connection: Connection) => endpoints.disconnect(connection.id),
    onSuccess: (_, connection) => {
      toast({ message: `Disconnected ${connection.account_email}.` });
      setLeaving(null);
      void client.invalidateQueries({ queryKey: CONNECTIONS_KEY });
    },
    onError: () => toast({ variant: "error", message: "Couldn't disconnect the account. Try again." }),
  });

  const start = () => {
    setExplaining(false);
    setProblem(null);
    void connect();
  };
  const connectButton = (
    <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => setExplaining(true)} disabled={waiting}>
      Connect Google
    </Button>
  );

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
            {connections.data.map((connection) => (
              <ConnectionRow
                key={connection.id}
                connection={connection}
                busy={waiting}
                onReconnect={() => setExplaining(true)}
                onDisconnect={() => setLeaving(connection)}
              />
            ))}
          </ul>
        )}

        <p className="flex items-center gap-2 text-body-sm text-text-muted">
          <ShieldCheck size={16} aria-hidden />
          {SECURITY}
        </p>
      </PageBody>

      <Dialog
        open={explaining}
        onClose={() => setExplaining(false)}
        title="Connect Google"
        description={EXPLAIN}
        footer={
          <>
            <Button onClick={() => setExplaining(false)}>Cancel</Button>
            <Button variant="primary" onClick={start}>
              Continue to Google
            </Button>
          </>
        }
      >
        <p className="text-body-sm text-text-muted">
          You choose the account and can untick any of the three. {SECURITY}
        </p>
      </Dialog>

      <ConfirmDialog
        open={leaving !== null}
        onClose={() => setLeaving(null)}
        onConfirm={() => leaving && disconnect.mutate(leaving)}
        loading={disconnect.isPending}
        title={leaving ? `Disconnect ${leaving.account_email}?` : "Disconnect"}
        description={
          leaving && leaving.used_by > 0
            ? `${usedBy(leaving.used_by)}. Their steps that publish or send as this account will need another account before they can run.`
            : "Isnad will forget this account and ask Google to revoke its access."
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

function ConnectionRow({
  connection,
  busy,
  onReconnect,
  onDisconnect,
}: {
  connection: Connection;
  busy: boolean;
  onReconnect: () => void;
  onDisconnect: () => void;
}) {
  const status = connectionStatus(connection);
  const { icon: Icon, className } = TONE[status.tone];
  return (
    <li className="grid gap-3 rounded-md border border-border bg-surface p-4 shadow-1 sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <GoogleLogo size={24} />
      <div className="grid min-w-0 gap-1">
        <p className="truncate text-body-md font-medium text-text">{connection.account_email}</p>
        <p className="text-body-sm text-text-muted">
          {connection.scopes.length ? connection.scopes.join(" · ") : "No services allowed — reconnect and tick YouTube, Drive or Gmail"}
        </p>
        <p className={`flex items-center gap-1.5 text-body-sm ${className}`}>
          <Icon size={14} aria-hidden />
          {status.text}
        </p>
        <p className="text-body-sm text-text-muted">{usedBy(connection.used_by)}</p>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={onReconnect} disabled={busy} aria-label={`Reconnect ${connection.account_email}`}>
          Reconnect
        </Button>
        <Button size="sm" variant="dangerSecondary" onClick={onDisconnect} aria-label={`Disconnect ${connection.account_email}`}>
          Disconnect
        </Button>
      </div>
    </li>
  );
}
