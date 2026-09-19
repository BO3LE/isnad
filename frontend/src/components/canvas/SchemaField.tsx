import { CircleAlert, Link2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/design-system/components/Button";
import { Field } from "@/design-system/components/Field";
import { Input, NumberInput, Textarea } from "@/design-system/components/Input";
import { Segmented } from "@/design-system/components/Segmented";
import { Select } from "@/design-system/components/Select";
import { Switch } from "@/design-system/components/Switch";
import { TagInput } from "@/design-system/components/TagInput";
import { withArticle, type Provider } from "@/lib/handover";
import { checkItem, checkValue, isEmpty, type FormField } from "@/lib/schema";

// One setting, rendered from its schema (DESIGN-SYSTEM §17.1) and told where its value comes from
// (UX-SPEC rule 1). The same component draws every field of every agent — there is no per-agent
// code, so a seventh agent gets a working form for free (AT-12).
//
// It never writes a default. It only calls onChange with what the user did, and an emptied field
// arrives as undefined so the caller removes it (UX-SPEC §4.5).

export interface SchemaFieldProps {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  /** Called once when the user starts changing this field, so undo can snapshot before it. */
  onBeginEdit: () => void;
  /** What an earlier step would supply if this field were left empty. */
  fallback: Provider | null;
  /** When nothing earlier supplies it but some agent could: "Writer". */
  couldComeFrom: string | null;
  /** The signed-in user's address, offered as a one-click recipient. */
  userEmail: string | null;
}

/** The inherit chip — the idea the whole UX turns on. */
export function InheritChip({ from, action, tone = "ok" }: { from: ReactNode; action?: ReactNode; tone?: "ok" | "broken" }) {
  return (
    <div
      className={`flex min-h-9 items-center gap-2 rounded-sm border border-dashed px-2.5 py-1.5 text-body-sm ${
        tone === "broken"
          ? "border-status-failed-solid bg-status-failed-bg text-status-failed-fg"
          : "border-border-strong bg-bg-sunken text-text"
      }`}
    >
      {tone === "broken" ? <TriangleAlert size={14} aria-hidden className="shrink-0" /> : <Link2 size={14} aria-hidden className="shrink-0 text-text-muted" />}
      <span className="min-w-0 flex-1">{from}</span>
      {action}
    </div>
  );
}

export function ProviderText({ provider }: { provider: Provider }) {
  return (
    <>
      From <span className="font-medium">{provider.agentTitle}</span> · {provider.outputTitle}
    </>
  );
}

const DefaultHint = () => <span className="text-overline uppercase text-text-subtle">Default</span>;

export function SchemaField({ field, value, onChange, onBeginEdit, fallback, couldComeFrom, userEmail }: SchemaFieldProps) {
  const [error, setError] = useState<string | null>(null);
  const [overriding, setOverriding] = useState(false);
  // What is in a number box while it is being typed, so clearing it doesn't snap back to the default.
  const [draft, setDraft] = useState<string | null>(null);
  const began = useRef(false);
  const focusRef = useRef<HTMLElement | null>(null);

  const empty = isEmpty(value);
  const usingDefault = value === undefined && field.hasDefault;

  useEffect(() => {
    if (overriding) focusRef.current?.focus();
  }, [overriding]);

  function begin() {
    if (began.current) return;
    began.current = true;
    onBeginEdit();
  }
  const end = () => {
    began.current = false;
  };

  function change(next: unknown) {
    begin();
    onChange(isEmpty(next) ? undefined : next);
  }

  function blurCheck(next: unknown) {
    end();
    setError(checkValue(field, next));
  }

  // --- Left empty, and an earlier step supplies it: show where it comes from, not a blank box.
  if (fallback && empty && !overriding && field.widget !== "credential") {
    return (
      <Field label={field.title} required={field.required} help="Leave it like this to use it.">
        {() => (
          <InheritChip
            from={<ProviderText provider={fallback} />}
            action={
              <Button variant="link" size="sm" onClick={() => setOverriding(true)}>
                Use my own
              </Button>
            }
          />
        )}
      </Field>
    );
  }

  let help: ReactNode = field.description;
  if (fallback) {
    help = (
      <>
        Your own value, used instead of {fallback.agentTitle}'s {fallback.outputTitle}.{" "}
        <Button
          variant="link"
          size="sm"
          onClick={() => {
            setOverriding(false);
            setError(null);
            change(undefined);
          }}
        >
          Use {fallback.agentTitle}'s instead
        </Button>
      </>
    );
  } else if (empty && couldComeFrom && field.widget !== "credential") {
    help = `Type one, or add ${withArticle(couldComeFrom)} before this step to fill it in.`;
  }

  const setRef = (element: HTMLElement | null) => {
    focusRef.current = element;
  };

  return (
    <Field label={field.title} required={field.required} help={help} error={error}>
      {({ id, describedBy, invalid }) => {
        switch (field.widget) {
          case "text":
            return (
              <Input
                ref={setRef}
                id={id}
                aria-describedby={describedBy}
                invalid={invalid}
                value={typeof value === "string" ? value : ""}
                // A default reads as a default: shown, not written (UX-SPEC §4.5 rule 2).
                placeholder={typeof field.default === "string" ? field.default : undefined}
                maxLength={field.maxLength}
                onChange={(event) => change(event.target.value)}
                onBlur={(event) => blurCheck(event.target.value)}
              />
            );
          case "textarea":
            return (
              <Textarea
                ref={setRef}
                id={id}
                aria-describedby={describedBy}
                invalid={invalid}
                value={typeof value === "string" ? value : ""}
                maxLength={field.maxLength}
                onChange={(event) => change(event.target.value)}
                onBlur={(event) => blurCheck(event.target.value)}
              />
            );
          case "number": {
            const shown = draft ?? String(value ?? (field.hasDefault ? field.default : ""));
            return (
              <div className="flex items-center gap-3">
                <div className="w-40">
                  <NumberInput
                    ref={setRef}
                    id={id}
                    aria-describedby={describedBy}
                    invalid={invalid}
                    unit={field.unit}
                    min={field.minimum}
                    max={field.maximum}
                    value={shown}
                    onChange={(event) => {
                      setDraft(event.target.value);
                      change(event.target.value === "" ? undefined : Number(event.target.value));
                    }}
                    onBlur={(event) => {
                      setDraft(null);
                      blurCheck(event.target.value === "" ? undefined : Number(event.target.value));
                    }}
                  />
                </div>
                {usingDefault && <DefaultHint />}
              </div>
            );
          }
          case "segmented":
            return (
              <div className="flex flex-wrap items-center gap-3">
                <Segmented
                  label={field.title}
                  options={field.options}
                  value={String(value ?? field.default ?? "")}
                  onChange={(next) => {
                    change(next);
                    end();
                  }}
                />
                {usingDefault && <DefaultHint />}
              </div>
            );
          case "select":
            return (
              <div className="grid gap-1.5">
                <Select
                  id={id}
                  aria-describedby={describedBy}
                  options={field.options}
                  placeholder={field.hasDefault ? undefined : "Choose one"}
                  value={String(value ?? field.default ?? "")}
                  onChange={(event) => {
                    change(event.target.value);
                    end();
                  }}
                />
                {usingDefault && <DefaultHint />}
              </div>
            );
          case "switch":
            return (
              <Switch
                label={field.title}
                hideLabel
                checked={Boolean(value ?? field.default)}
                onChange={(next) => {
                  change(next);
                  end();
                }}
              />
            );
          case "tags": {
            const items = Array.isArray(value) ? (value as string[]) : [];
            const offerSelf = field.itemFormat === "email" && userEmail && !items.includes(userEmail);
            return (
              <div className="grid justify-items-start gap-1.5">
                <TagInput
                  id={id}
                  label={field.title}
                  value={items}
                  describedBy={describedBy}
                  invalid={invalid}
                  placeholder={field.itemFormat === "email" ? "Type an address, then Enter" : "Type, then Enter"}
                  check={(item) => checkItem(field, item)}
                  onError={setError}
                  onFocus={begin}
                  onChange={(next) => {
                    change(next);
                    end();
                  }}
                />
                {offerSelf && (
                  <Button variant="link" size="sm" onClick={() => change([...items, userEmail])}>
                    Send it to me ({userEmail})
                  </Button>
                )}
              </div>
            );
          }
          case "credential":
            // Secrets are never text fields (UX-SPEC §4.5 rule 4). Connecting an account needs the
            // credentials endpoints (D-09), which don't exist yet.
            return empty ? (
              <div className="grid justify-items-start gap-2">
                <InheritChip tone="broken" from={`No ${field.provider === "google" ? "Google " : ""}account connected`} />
                <Button size="sm" disabled title="Connections aren't available yet">
                  Connect {field.provider === "google" ? "Google" : "an account"}
                </Button>
              </div>
            ) : (
              <InheritChip from="Account connected" />
            );
          default:
            return (
              <div className="grid gap-1.5">
                <pre className="overflow-x-auto rounded-sm bg-bg-sunken p-2 font-mono text-mono-sm text-text-muted">
                  {value === undefined ? "Not set" : JSON.stringify(value, null, 2)}
                </pre>
                <p className="flex items-center gap-1.5 text-body-sm text-text-muted">
                  <CircleAlert size={14} aria-hidden />
                  This setting can't be changed here yet.
                </p>
              </div>
            );
        }
      }}
    </Field>
  );
}
