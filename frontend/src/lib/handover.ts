import type { AgentManifest } from "./api";
import type { components } from "./api-types";
import type { FlowEdgeLike } from "./graph";
import { isEmpty, type Configuration } from "./schema";

// How a chain hands work from one step to the next (UX-SPEC §2).
//
// The orchestrator merges the outputs of every earlier connected step, in run order, then lays the
// step's own settings on top, and validates the result against the agent's input model. Each
// input accepts some output names — Video's `script` accepts Writer's `article_md`. This file
// replays that rule on the canvas, from what the catalog publishes, so every field can say where
// its value will come from before anything runs.

export type AgentInput = components["schemas"]["AgentInput"];

/** "a Writer", "an Image". */
export function withArticle(title: string): string {
  return `${/^[aeiou]/i.test(title) ? "an" : "a"} ${title}`;
}

export interface StepLike {
  id: string;
  agentType: string;
  configuration: Configuration;
}

export interface Provider {
  stepId: string;
  agentTitle: string;
  /** The output name as the step hands it on, e.g. `article_md`. */
  output: string;
  /** What a person calls it, e.g. "article". */
  outputTitle: string;
}

export type ValueSource =
  /** The user typed it; it overrides anything earlier steps produce. */
  | { kind: "own" }
  /** Left empty, so it arrives from an earlier step. */
  | { kind: "inherited"; from: Provider }
  /** Optional and nothing supplies it: the agent's own default applies. */
  | { kind: "default" }
  /** Required, and nothing will supply it. `needs` names the agent that could. */
  | { kind: "missing"; needs: string | null; wants: string[] };

const manifestOf = (catalog: AgentManifest[], agentType: string) => catalog.find((a) => a.name === agentType);

function outputTitle(manifest: AgentManifest | undefined, name: string): string {
  return manifest?.outputs?.find((o) => o.name === name)?.title ?? name.replace(/_/g, " ");
}

/** Steps in run order: parents before children, ties kept in canvas order. */
export function runOrder(stepIds: string[], edges: FlowEdgeLike[]): string[] {
  const incoming = new Map(stepIds.map((id) => [id, 0]));
  for (const e of edges) if (incoming.has(e.target) && incoming.has(e.source)) incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
  const order: string[] = [];
  let ready = stepIds.filter((id) => incoming.get(id) === 0);
  while (ready.length > 0) {
    const next: string[] = [];
    for (const id of ready) {
      order.push(id);
      for (const e of edges) {
        if (e.source !== id || !incoming.has(e.target)) continue;
        const left = (incoming.get(e.target) ?? 1) - 1;
        incoming.set(e.target, left);
        if (left === 0) next.push(e.target);
      }
    }
    ready = next.sort((a, b) => stepIds.indexOf(a) - stepIds.indexOf(b));
  }
  return order;
}

export function ancestorsOf(stepId: string, edges: FlowEdgeLike[]): Set<string> {
  const found = new Set<string>();
  const frontier = edges.filter((e) => e.target === stepId).map((e) => e.source);
  while (frontier.length > 0) {
    const current = frontier.pop()!;
    if (found.has(current)) continue;
    found.add(current);
    for (const e of edges) if (e.target === current) frontier.push(e.source);
  }
  return found;
}

/** Everything the earlier steps will have handed on by the time `stepId` runs. Later steps win. */
export function availableTo(stepId: string, steps: StepLike[], edges: FlowEdgeLike[], catalog: AgentManifest[]): Map<string, Provider> {
  const ancestors = ancestorsOf(stepId, edges);
  const byId = new Map(steps.map((s) => [s.id, s]));
  const available = new Map<string, Provider>();
  for (const id of runOrder(steps.map((s) => s.id), edges)) {
    if (!ancestors.has(id)) continue;
    const step = byId.get(id)!;
    const manifest = manifestOf(catalog, step.agentType);
    for (const output of manifest?.outputs ?? []) {
      available.set(output.name, {
        stepId: id,
        agentTitle: manifest?.title ?? step.agentType,
        output: output.name,
        outputTitle: output.title,
      });
    }
  }
  return available;
}

/** The agent that could supply one of these names — "add a Writer before this step". */
export function producerOf(names: string[], catalog: AgentManifest[], except?: string): AgentManifest | null {
  for (const name of names) {
    const match = catalog.find((a) => a.name !== except && a.outputs?.some((o) => o.name === name));
    if (match) return match;
  }
  return null;
}

export function sourceOf(input: AgentInput, step: StepLike, available: Map<string, Provider>, catalog: AgentManifest[]): ValueSource {
  if (input.settable && !isEmpty(step.configuration[input.name])) return { kind: "own" };
  for (const name of input.accepts) {
    const provider = available.get(name);
    if (provider) return { kind: "inherited", from: provider };
  }
  if (!input.required) return { kind: "default" };
  const producer = producerOf(input.accepts, catalog, step.agentType);
  const wants = input.accepts.map((name) => outputTitle(producer ?? undefined, name));
  return { kind: "missing", needs: producer?.title ?? null, wants };
}

export interface StepHandover {
  /** Per input name. */
  sources: Map<string, ValueSource>;
  /** Short lines for the node face: "Needs a Researcher before this step". */
  needs: string[];
  /** What earlier steps will hand on — what an emptied field would fall back to. */
  available: Map<string, Provider>;
}

/** What a settable field would use if the user left it empty. */
export function fallbackFor(input: AgentInput | undefined, available: Map<string, Provider>): Provider | null {
  for (const name of input?.accepts ?? []) {
    const provider = available.get(name);
    if (provider) return provider;
  }
  return null;
}

export function describeStep(step: StepLike, steps: StepLike[], edges: FlowEdgeLike[], catalog: AgentManifest[]): StepHandover {
  const manifest = manifestOf(catalog, step.agentType);
  const available = availableTo(step.id, steps, edges, catalog);
  const requiredSettings = new Set((manifest?.config_schema?.required as string[] | undefined) ?? []);
  const sources = new Map<string, ValueSource>();
  const needs = new Set<string>();

  for (const input of manifest?.inputs ?? []) {
    const source = sourceOf(input, step, available, catalog);
    sources.set(input.name, source);
    if (source.kind !== "missing") continue;
    // A required setting nothing could supply is already reported as "Missing: topic".
    if (requiredSettings.has(input.name)) continue;
    const label = input.name.replace(/_/g, " ");
    if (input.settable) {
      needs.add(source.needs ? `Missing: ${label} — or add ${withArticle(source.needs)} before it` : `Missing: ${label}`);
    } else {
      needs.add(source.needs ? `Needs ${withArticle(source.needs)} before this step` : `Needs ${source.wants[0]} from an earlier step`);
    }
  }
  return { sources, needs: [...needs], available };
}

/**
 * What crosses a connection: the source's outputs that the target reads. "notes · sources".
 * Empty means the target can't use anything the source makes — Email → Writer.
 */
export function handover(sourceType: string, targetType: string, catalog: AgentManifest[]): string[] {
  const source = manifestOf(catalog, sourceType);
  const target = manifestOf(catalog, targetType);
  const wanted = new Set((target?.inputs ?? []).flatMap((input) => input.accepts));
  return (source?.outputs ?? []).filter((o) => wanted.has(o.name)).map((o) => o.title);
}
