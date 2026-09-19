import { Hand } from "lucide-react";
import { useEffect, useState } from "react";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { Button } from "@/design-system/components/Button";
import { Dialog } from "@/design-system/components/Dialog";
import { Field } from "@/design-system/components/Field";
import { Textarea } from "@/design-system/components/Input";
import type { AgentManifest } from "@/lib/api";
import { fallbackFor, type StepHandover } from "@/lib/handover";
import { isEmpty, optionLabel, resolveFields, type Configuration, type FormField } from "@/lib/schema";

// S-06 on the canvas (UX-SPEC §7): "What exactly is about to go out under my name?"
//
// The step is parked before it acts, so nothing has left the platform. The destination is read from
// the step's settings and what earlier steps hand on — generically, from the schema. The preview of
// the real files needs GET /runs/{run_id}/outputs, which the API does not have yet; until then the
// dialog says so rather than pretending.

export interface ApprovalDialogProps {
  open: boolean;
  onClose: () => void;
  stepTitle: string;
  manifest: AgentManifest | undefined;
  configuration: Configuration;
  handover: StepHandover | undefined;
  /** Later steps that will ask again, e.g. "Email". */
  laterGates: string[];
  onApprove: () => void;
  onReject: (note: string) => void;
  deciding: boolean;
}

function shownValue(field: FormField, value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (field.options.length > 0) return optionLabel(field, value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** "Approve and send to YouTube", "Approve and send to 1 recipient" — the consequence, never "OK". */
function approveLabel(stepTitle: string, fields: FormField[], configuration: Configuration): string {
  const choice = fields.find((f) => f.options.length > 0);
  if (choice) return `Approve and send to ${optionLabel(choice, configuration[choice.key] ?? choice.default)}`;
  const list = fields.find((f) => f.widget === "tags" && Array.isArray(configuration[f.key]));
  if (list) {
    const count = (configuration[list.key] as unknown[]).length;
    return `Approve and send to ${count} ${list.itemFormat === "email" ? (count === 1 ? "recipient" : "recipients") : list.title.toLowerCase()}`;
  }
  return `Approve and run ${stepTitle}`;
}

export function ApprovalDialog({
  open,
  onClose,
  stepTitle,
  manifest,
  configuration,
  handover,
  laterGates,
  onApprove,
  onReject,
  deciding,
}: ApprovalDialogProps) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setRejecting(false);
      setNote("");
      setNoteError(null);
    }
  }, [open]);

  const fields = resolveFields(manifest?.config_schema);
  const inputs = manifest?.inputs ?? [];
  const available = handover?.available ?? new Map();

  const rows: { label: string; value: string }[] = [];
  for (const input of inputs.filter((i) => !i.settable)) {
    const provider = fallbackFor(input, available);
    if (provider) rows.push({ label: input.name.replace(/_path$/, "").replace(/_/g, " "), value: `From ${provider.agentTitle} · ${provider.outputTitle}` });
  }
  for (const field of fields) {
    const value = configuration[field.key];
    const provider = fallbackFor(
      inputs.find((i) => i.name === field.key),
      available,
    );
    if (!isEmpty(value)) rows.push({ label: field.title, value: field.widget === "credential" ? "Connected account" : shownValue(field, value) });
    else if (provider) rows.push({ label: field.title, value: `From ${provider.agentTitle} · ${provider.outputTitle}` });
    else if (field.widget === "credential") rows.push({ label: field.title, value: "Not connected" });
    else if (field.hasDefault) rows.push({ label: field.title, value: shownValue(field, field.default) });
  }

  function reject() {
    if (!note.trim()) {
      setNoteError("Add a note — it's kept with the run.");
      return;
    }
    onReject(note.trim());
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="content"
      title="Review before it goes out"
      description={
        <>
          {stepTitle} is waiting for your approval. <strong className="font-medium text-text">Nothing has been sent yet.</strong>
        </>
      }
      footer={
        rejecting ? (
          <>
            <Button variant="ghost" onClick={() => setRejecting(false)} disabled={deciding}>
              Back
            </Button>
            <Button variant="danger" onClick={reject} loading={deciding}>
              Reject and stop the run
            </Button>
          </>
        ) : (
          <>
            <Button variant="dangerSecondary" onClick={() => setRejecting(true)} disabled={deciding}>
              Reject…
            </Button>
            <Button variant="primary" onClick={onApprove} loading={deciding}>
              {approveLabel(stepTitle, fields, configuration)}
            </Button>
          </>
        )
      }
    >
      <div className="grid gap-4">
        <div className="flex items-start gap-3 rounded-sm border-l-[3px] border-status-approval-solid bg-status-approval-bg px-4 py-3">
          <Hand size={16} aria-hidden className="mt-0.5 shrink-0 text-status-approval-fg" />
          <p className="text-body-md text-text">
            Approving lets {stepTitle} run now. Rejecting stops the run, and you'll be asked why.
          </p>
        </div>

        <section className="grid gap-3 rounded-md border border-border p-4" aria-labelledby="approval-destination">
          <div className="flex items-center gap-2">
            {manifest && <AgentIcon icon={manifest.icon} family={manifest.family} size="sm" />}
            <h3 id="approval-destination" className="text-overline uppercase text-text-muted">
              Where this goes
            </h3>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-sm">
            {rows.map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-text-muted first-letter:uppercase">{row.label}</dt>
                <dd className="m-0 break-words text-right text-text">{row.value}</dd>
              </div>
            ))}
          </dl>
          {laterGates.length > 0 && (
            <p className="text-body-sm text-text-muted">
              After this, {laterGates.join(" and ")} will ask you again before it acts.
            </p>
          )}
        </section>

        <section className="grid gap-1 rounded-md border border-dashed border-border-strong bg-bg-sunken p-4" aria-label="Preview">
          <p className="text-body-md font-medium text-text">Preview isn't available yet</p>
          <p className="text-body-sm text-text-muted">
            The platform can't list the files this run made yet, so they can't be shown here. What {stepTitle} will use is
            listed above.
          </p>
        </section>

        {rejecting && (
          <Field label="Why are you rejecting this?" required error={noteError}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                aria-describedby={describedBy}
                invalid={invalid}
                autoFocus
                value={note}
                onChange={(event) => {
                  setNote(event.target.value);
                  if (noteError) setNoteError(null);
                }}
                placeholder="Wrong thumbnail, the title needs work…"
              />
            )}
          </Field>
        )}
      </div>
    </Dialog>
  );
}
