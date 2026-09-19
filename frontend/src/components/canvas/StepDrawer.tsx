import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { Banner } from "@/design-system/components/Banner";
import { IconButton } from "@/design-system/components/IconButton";
import { Switch } from "@/design-system/components/Switch";
import { Tabs } from "@/design-system/components/Tabs";
import type { AgentManifest, ValidationResult } from "@/lib/api";
import { fallbackFor, producerOf, withArticle, type StepHandover } from "@/lib/handover";
import { resolveFields, setValue, type Configuration } from "@/lib/schema";
import type { AgentNodeData } from "./AgentNode";
import { InheritChip, ProviderText, SchemaField } from "./SchemaField";

// S-04 · the step's settings (DESIGN-SYSTEM §17.6, UX-SPEC §4.5) — how a person gives a step its
// orders. Built entirely from the catalog: the agent's config schema draws the form, and its
// published inputs say which values arrive from earlier steps.
//
// There is no Save button. Every change goes into the canvas graph and the page's 800 ms autosave.

type Issue = ValidationResult["issues"][number];

export interface StepDrawerProps {
  stepId: string;
  data: AgentNodeData;
  manifest: AgentManifest | undefined;
  catalog: AgentManifest[];
  handover: StepHandover;
  issues: Issue[];
  saveLabel: string;
  userEmail: string | null;
  onConfigurationChange: (configuration: Configuration) => void;
  onApprovalChange: (requiresApproval: boolean) => void;
  onBeginEdit: () => void;
  onClose: () => void;
}

const inputLabel = (name: string) => {
  const words = name.replace(/_path$/, "").replace(/_md$/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};

export function StepDrawer({
  stepId,
  data,
  manifest,
  catalog,
  handover,
  issues,
  saveLabel,
  userEmail,
  onConfigurationChange,
  onApprovalChange,
  onBeginEdit,
  onClose,
}: StepDrawerProps) {
  const [tab, setTab] = useState("settings");
  const fields = useMemo(() => resolveFields(manifest?.config_schema), [manifest]);
  const inputs = manifest?.inputs ?? [];
  const locked = manifest?.requires_approval === true;

  useEffect(() => setTab("settings"), [stepId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Values only an earlier step can supply: Writer's notes, Video's script, Publisher's file.
  const handed = inputs.filter((input) => !input.settable && (input.required || handover.sources.get(input.name)?.kind === "inherited"));
  const anyRequired = fields.some((f) => f.required) || handed.some((i) => i.required);

  return (
    <aside
      aria-label={`${data.title} settings`}
      className="absolute inset-y-0 right-0 z-drawer flex w-full max-w-[400px] flex-col border-l border-border bg-surface shadow-3 lg:static lg:w-[400px] lg:shadow-none"
    >
      <header className="flex h-16 shrink-0 items-center gap-3 border-b border-border px-4">
        <AgentIcon agentType={data.agentType} icon={data.icon} family={data.family} size="lg" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-heading-md text-text">{data.title}</h2>
          <p className="text-overline uppercase text-text-muted">
            {data.agentType.replace(/_/g, " ")}
            {data.step ? ` · Step ${data.step}` : ""}
          </p>
        </div>
        <IconButton label="Close settings" icon={<X size={16} aria-hidden />} onClick={onClose} />
      </header>

      <Tabs
        label="Step panels"
        className="px-4"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "settings", label: "Settings" },
          { id: "output", label: "Last output" },
        ]}
      />

      {tab === "settings" ? (
        <div className="grid min-h-0 flex-1 content-start gap-5 overflow-y-auto p-4">
          {manifest?.description && <p className="text-body-md text-text-muted">{manifest.description}</p>}

          {/* The server owns validation; its words are shown as they are (§15.5). */}
          {issues.length > 0 && (
            <Banner variant="error">
              <ul className="grid list-none gap-1">
                {issues.map((issue) => (
                  <li key={`${issue.code}-${issue.message}`}>{issue.message}</li>
                ))}
              </ul>
            </Banner>
          )}

          {anyRequired && <p className="-mb-2 text-body-sm text-text-muted">Fields marked * are required.</p>}

          {handed.length > 0 && (
            <section className="grid gap-3" aria-labelledby={`${stepId}-handed`}>
              <h3 id={`${stepId}-handed`} className="text-overline uppercase text-text-muted">
                From earlier steps
              </h3>
              {handed.map((input) => {
                const source = handover.sources.get(input.name);
                return (
                  <div key={input.name} className="grid gap-1.5">
                    <p className="text-body-md font-medium text-text">
                      {inputLabel(input.name)}
                      {input.required && (
                        <span aria-hidden className="text-status-failed-fg">
                          {" *"}
                        </span>
                      )}
                    </p>
                    {source?.kind === "inherited" ? (
                      <>
                        <InheritChip from={<ProviderText provider={source.from} />} />
                        <p className="text-body-sm text-text-muted">Filled in automatically when {source.from.agentTitle} finishes.</p>
                      </>
                    ) : source?.kind === "missing" ? (
                      <>
                        <InheritChip
                          tone="broken"
                          from={source.needs ? `Needs ${withArticle(source.needs)} before this step` : `Needs ${source.wants[0]} from an earlier step`}
                        />
                        <p className="text-body-sm text-text-muted">
                          {source.needs
                            ? `Drag ${source.needs} onto the canvas and connect it to this step.`
                            : "Connect a step that produces it."}
                        </p>
                      </>
                    ) : null}
                  </div>
                );
              })}
            </section>
          )}

          {fields.length > 0 && (
            <section className="grid gap-5" aria-label="Settings">
              {handed.length > 0 && <h3 className="-mb-2 text-overline uppercase text-text-muted">Your settings</h3>}
              {fields.map((field) => {
                const input = inputs.find((i) => i.name === field.key);
                const fallback = input ? fallbackFor(input, handover.available) : null;
                const producer = input?.required ? producerOf(input.accepts, catalog, data.agentType) : null;
                return (
                  <SchemaField
                    key={`${stepId}-${field.key}`}
                    field={field}
                    value={data.configuration[field.key]}
                    fallback={fallback}
                    couldComeFrom={producer?.title ?? null}
                    userEmail={userEmail}
                    onBeginEdit={onBeginEdit}
                    onChange={(next) => onConfigurationChange(setValue(data.configuration, field.key, next))}
                  />
                );
              })}
            </section>
          )}

          {fields.length === 0 && handed.length === 0 && (
            <p className="text-body-md text-text-muted">This step has nothing to set. It works with what earlier steps hand on.</p>
          )}
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 content-start gap-2 overflow-y-auto p-4">
          <p className="text-body-md font-medium text-text">Nothing to show yet</p>
          <p className="text-body-md text-text-muted">
            After this workflow runs, what {data.title} produced will appear here.
          </p>
        </div>
      )}

      <footer className="grid shrink-0 gap-1 border-t border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <Switch
            label="Require approval"
            description={locked ? "Always on — this step sends things outside the platform." : "Pause before this step until you approve."}
            checked={locked || data.requiresApproval}
            disabled={locked}
            onChange={(next) => {
              onBeginEdit();
              onApprovalChange(next);
            }}
          />
        </div>
        <p className="text-body-sm text-text-muted" aria-live="polite">
          {saveLabel || "Changes save automatically."}
        </p>
      </footer>
    </aside>
  );
}
