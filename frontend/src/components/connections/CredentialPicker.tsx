import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleX, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { GoogleLogo } from "./GoogleLogo";
import { CONNECTIONS_KEY, useConnectGoogle } from "./useConnectGoogle";
import { Button } from "@/design-system/components/Button";
import { Select } from "@/design-system/components/Select";
import { Skeleton } from "@/design-system/components/Skeleton";
import { endpoints } from "@/lib/api";
import { connectionStatus } from "@/lib/connections";
import type { FormField } from "@/lib/schema";

// DESIGN-SYSTEM §17.3 — which connected account a step acts as. The step stores only the
// connection's id (`credential_id`); the account's tokens never reach the browser or the graph.
// Drawn from the schema alone (`x-widget: credential`), so it names no agent (AT-12).

const TONE = {
  ok: { icon: CircleCheck, className: "text-status-success-fg" },
  warning: { icon: TriangleAlert, className: "text-status-retrying-fg" },
  danger: { icon: CircleX, className: "text-status-failed-fg" },
} as const;

export interface CredentialPickerProps {
  field: FormField;
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  id?: string;
}

export function CredentialPicker({ field, value, onChange, id }: CredentialPickerProps) {
  const provider = field.provider === "google" ? "Google" : "an";
  const connections = useQuery({ queryKey: CONNECTIONS_KEY, queryFn: endpoints.connections, enabled: field.connection !== "unused" });
  const { connect, cancel, waiting } = useConnectGoogle((fresh) => fresh && onChange(fresh.id));

  // This server does this step without an account (e.g. it sends email over its own SMTP).
  if (field.connection === "unused") {
    return <p className="text-body-sm text-text-muted">This server doesn't need an account for this step.</p>;
  }
  if (connections.isPending) return <Skeleton className="h-9 w-full" label="Loading your connections" />;
  if (connections.isError) {
    return (
      <p className="flex flex-wrap items-center gap-2 text-body-sm text-status-failed-fg">
        Couldn't load your connections.
        <Button variant="link" size="sm" onClick={() => void connections.refetch()}>
          Try again
        </Button>
      </p>
    );
  }

  const waitingNote = waiting && (
    <p className="flex flex-wrap items-center gap-2 text-body-sm text-text-muted" role="status">
      Waiting for Google — finish in the window that opened.
      <Button variant="link" size="sm" onClick={cancel}>
        Cancel
      </Button>
    </p>
  );
  const all = connections.data;
  if (all.length === 0) {
    return (
      <div className="grid justify-items-start gap-2">
        <p className="flex items-center gap-1.5 text-body-sm text-status-failed-fg">
          <TriangleAlert size={14} aria-hidden />
          No {provider} account connected
        </p>
        <Button size="sm" icon={<GoogleLogo size={14} />} onClick={() => void connect()} disabled={waiting}>
          Connect {provider === "an" ? "an account" : provider}
        </Button>
        {waitingNote}
      </div>
    );
  }

  const chosen = all.find((c) => c.id === value);
  const status = chosen ? connectionStatus(chosen) : null;
  const tone = status ? TONE[status.tone] : null;
  return (
    <div className="grid gap-1.5">
      <Select
        id={id}
        value={chosen ? chosen.id : ""}
        placeholder="Choose an account"
        invalid={!chosen && field.required}
        options={all.map((c) => ({
          value: c.id,
          label: c.status === "expired" ? `${c.account_email} (expired)` : c.account_email,
        }))}
        onChange={(event) => onChange(event.target.value || undefined)}
      />
      {value && !chosen && (
        <p className="flex items-center gap-1.5 text-body-sm text-status-failed-fg">
          <TriangleAlert size={14} aria-hidden />
          The account this step used was disconnected. Choose another.
        </p>
      )}
      {status && tone && (
        <p className={`flex items-center gap-1.5 text-body-sm ${tone.className}`}>
          <tone.icon size={14} aria-hidden />
          {status.text}
        </p>
      )}
      <div className="flex flex-wrap gap-x-4">
        <Button variant="link" size="sm" onClick={() => void connect()} disabled={waiting}>
          Connect another account
        </Button>
        <Link to="/settings/connections" className="text-caption text-accent-text underline-offset-2 hover:underline">
          Manage connections
        </Link>
      </div>
      {waitingNote}
    </div>
  );
}
