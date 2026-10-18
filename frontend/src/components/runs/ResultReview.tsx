import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";
import { Button } from "@/design-system/components/Button";
import { Field } from "@/design-system/components/Field";
import { Textarea } from "@/design-system/components/Input";
import { useToast } from "@/design-system/components/toast-context";
import { agentTitle } from "@/design-system/agents/agentMeta";
import { OutputBody, OutputLoading } from "@/components/runs/OutputPreview";
import { ApiError, endpoints, type AgentManifest, type Decision, type EditableField, type Edits, type NodeState } from "@/lib/api";

// A step the person asked to review has run and waits with its result. They approve it — as it is,
// or with their own changes to its text — send it back with a note to be redone, or stop the run.
//
// Nothing here knows an agent: what the result shows comes from its outputs, and what can be edited
// from the fields the agent marked editable (GET /runs/{id}/nodes/{node}/result) — so a seventh
// agent's result is reviewed like any other (AT-12).

type Mode = "view" | "edit" | "redo" | "stop";

export interface ResultReviewProps {
  runId: string;
  /** The step waiting with its result. */
  step: NodeState;
  agents?: AgentManifest[];
  /** The step that runs once this result is approved; null when this is the last. */
  nextTitle: string | null;
  onDecided?: () => void;
}

/** A field's value as the person edits it: a list of lines is one line each. */
function asText(field: EditableField): string {
  return Array.isArray(field.value) ? field.value.join("\n") : field.value;
}

function rowsFor(field: EditableField): number {
  const text = asText(field);
  const lines = text.split("\n").length;
  if (field.kind === "lines") return Math.min(12, Math.max(4, lines + 1));
  // A title or a summary is a line or two; anything with paragraphs (an article) gets room.
  if (lines === 1 && text.length < 120) return 2;
  return Math.min(24, Math.max(8, lines + 2, Math.ceil(text.length / 90)));
}

/** Only what the person actually changed, in the shape the API takes. */
function changes(fields: EditableField[], draft: Record<string, string>): Edits | undefined {
  const edits: Edits = {};
  for (const field of fields) {
    const text = draft[field.name] ?? asText(field);
    if (field.kind === "lines") {
      const lines = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      if (JSON.stringify(lines) !== JSON.stringify(field.value)) edits[field.name] = lines;
    } else if (text.trim() !== (field.value as string).trim()) {
      edits[field.name] = text;
    }
  }
  return Object.keys(edits).length > 0 ? edits : undefined;
}

export function ResultReview({ runId, step, agents, nextTitle, onDecided }: ResultReviewProps) {
  const title = agentTitle(step.agent_type, agents);
  const headingId = useId();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [mode, setMode] = useState<Mode>("view");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);

  // A redone step comes back as a new result: the review starts over on it.
  useEffect(() => {
    setMode("view");
    setDraft({});
    setNote("");
    setNoteError(null);
  }, [step.node_id, step.revision]);

  const outputs = useQuery({
    queryKey: ["run-outputs", runId, step.node_id, step.revision],
    queryFn: () => endpoints.runOutputs(runId),
  });
  const result = useQuery({
    queryKey: ["step-result", runId, step.node_id, step.revision],
    queryFn: () => endpoints.stepResult(runId, step.node_id),
  });

  const decide = useMutation({
    mutationFn: ({ decision, note, edits }: { decision: Decision; note?: string; edits?: Edits }) =>
      endpoints.approve(runId, step.node_id, decision, note, edits),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-outputs", runId] });
      onDecided?.();
    },
    onError: (error) =>
      toast({ variant: "error", message: error instanceof ApiError ? error.message : "Couldn't record your decision." }),
  });

  const editable = result.data?.editable ?? [];
  const mine = (outputs.data ?? []).filter((output) => output.node_id === step.node_id);
  const files = mine.filter((output) => output.kind !== "text");
  // A video's or an image's text is only where its file is stored: the file itself says it all.
  const shown = editable.length > 0 || files.length === 0 ? mine : files;
  const asked = step.revision > 0 && step.approval?.decision === "redo" ? step.approval.note : null;

  function back() {
    setMode("view");
    setNoteError(null);
  }

  function stop() {
    if (!note.trim()) {
      setNoteError("Add a note — it's kept with the run.");
      return;
    }
    decide.mutate({ decision: "reject", note: note.trim() });
  }

  return (
    <section aria-labelledby={headingId} className="grid gap-4 rounded-md border border-status-approval-solid bg-surface p-4">
      <header className="grid gap-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 id={headingId} className="text-heading-sm text-text">
            {title}&apos;s result
          </h2>
          {step.revision > 0 && (
            <span className="font-mono text-mono-sm text-text-muted">version {step.revision + 1}</span>
          )}
        </div>
        <p className="text-body-md text-text-muted">
          {nextTitle
            ? `${nextTitle} runs only after you approve this.`
            : "The run finishes when you approve this."}{" "}
          {asked ? <>You asked: &ldquo;{asked}&rdquo;</> : null}
        </p>
      </header>

      {mode === "edit" ? (
        <div className="grid gap-3">
          {editable.map((field) => (
            <Field
              key={field.name}
              label={field.title.charAt(0).toUpperCase() + field.title.slice(1)}
              help={field.kind === "lines" ? "One per line." : undefined}
            >
              {({ id, describedBy }) => (
                <Textarea
                  id={id}
                  aria-describedby={describedBy}
                  rows={rowsFor(field)}
                  value={draft[field.name] ?? asText(field)}
                  onChange={(event) => setDraft((current) => ({ ...current, [field.name]: event.target.value }))}
                />
              )}
            </Field>
          ))}
        </div>
      ) : outputs.isPending ? (
        <OutputLoading />
      ) : shown.length === 0 ? (
        <p className="text-body-md text-text-muted">This step finished without anything to show.</p>
      ) : (
        <div className="grid gap-4">
          {shown.map((output) => (
            <OutputBody key={output.id} output={output} roomy />
          ))}
        </div>
      )}

      {mode === "redo" && (
        <Field label="What should change?" help={`${title} runs again with your note, and you review the new result.`}>
          {({ id, describedBy }) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              autoFocus
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Make it shorter, focus on costs, use more recent sources…"
            />
          )}
        </Field>
      )}

      {mode === "stop" && (
        <Field label="Why are you stopping the run?" required error={noteError}>
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
              placeholder="Wrong topic, not what I need…"
            />
          )}
        </Field>
      )}

      <footer className="flex flex-wrap items-center gap-2">
        {mode === "view" && (
          <>
            <Button variant="primary" onClick={() => decide.mutate({ decision: "approve" })} loading={decide.isPending}>
              {nextTitle ? `Approve and run ${nextTitle}` : "Approve and finish"}
            </Button>
            {editable.length > 0 && (
              <Button onClick={() => setMode("edit")} disabled={decide.isPending}>
                Edit
              </Button>
            )}
            <Button onClick={() => setMode("redo")} disabled={decide.isPending}>
              Redo with a note…
            </Button>
            <Button variant="dangerSecondary" onClick={() => setMode("stop")} disabled={decide.isPending}>
              Stop the run…
            </Button>
          </>
        )}
        {mode === "edit" && (
          <>
            <Button
              variant="primary"
              onClick={() => decide.mutate({ decision: "approve", edits: changes(editable, draft) })}
              loading={decide.isPending}
            >
              {nextTitle ? `Approve my version and run ${nextTitle}` : "Approve my version"}
            </Button>
            <Button variant="ghost" onClick={back} disabled={decide.isPending}>
              Discard changes
            </Button>
          </>
        )}
        {mode === "redo" && (
          <>
            <Button
              variant="primary"
              onClick={() => decide.mutate({ decision: "redo", note: note.trim() || undefined })}
              loading={decide.isPending}
            >
              Redo {title}
            </Button>
            <Button variant="ghost" onClick={back} disabled={decide.isPending}>
              Back
            </Button>
          </>
        )}
        {mode === "stop" && (
          <>
            <Button variant="danger" onClick={stop} loading={decide.isPending}>
              Stop the run
            </Button>
            <Button variant="ghost" onClick={back} disabled={decide.isPending}>
              Back
            </Button>
          </>
        )}
      </footer>
    </section>
  );
}
