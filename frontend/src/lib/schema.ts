// An agent's configuration JSON Schema, read the way a person needs it (UX-SPEC §4.5,
// DESIGN-SYSTEM §17). Every form, label and node summary comes from here — there is no per-agent
// code anywhere, because the moment there is, a seventh agent needs a developer (AT-12).

export type Configuration = Record<string, unknown>;
type JsonSchema = Record<string, unknown>;

export type Widget = "text" | "textarea" | "number" | "segmented" | "select" | "switch" | "tags" | "credential" | "unsupported";

export interface FieldOption {
  value: string;
  label: string;
}

export interface FormField {
  key: string;
  title: string;
  description?: string;
  required: boolean;
  widget: Widget;
  options: FieldOption[];
  /** The agent's own default. Shown as a default, never written into the configuration. */
  default?: unknown;
  hasDefault: boolean;
  unit?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  /** `email` for recipient lists, so the form checks addresses without knowing the agent. */
  itemFormat?: string;
  provider?: string;
}

/** `str | None` arrives as `anyOf: [{type: string, ...}, {type: null}]`. Merge the real branch up. */
export function unwrap(property: JsonSchema): JsonSchema {
  const anyOf = property.anyOf;
  if (!Array.isArray(anyOf)) return property;
  const real = anyOf.filter((branch: JsonSchema) => branch?.type !== "null");
  if (real.length !== 1) return property;
  const { anyOf: _drop, ...rest } = property;
  void _drop;
  return { ...(real[0] as JsonSchema), ...rest };
}

export function humanise(value: string): string {
  const spaced = value.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** `null`, `""` and `[]` all mean "not set" — the same rule `/validate` uses. */
export function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

/**
 * The one write path into a step's settings. A cleared field is removed, never stored empty:
 * the orchestrator lays `configuration` over what earlier steps produced, so an empty value
 * would overwrite, say, Writer's title and break the chain (UX-SPEC §4.5).
 */
export function setValue(configuration: Configuration, key: string, value: unknown): Configuration {
  const next = { ...configuration };
  if (isEmpty(value)) delete next[key];
  else next[key] = value;
  return next;
}

function widgetFor(property: JsonSchema, options: FieldOption[]): Widget {
  if (property["x-widget"] === "credential") return "credential";
  if (options.length > 0) return options.length <= 3 ? "segmented" : "select";
  switch (property.type) {
    case "boolean":
      return "switch";
    case "integer":
    case "number":
      return "number";
    case "array": {
      const items = property.items as JsonSchema | undefined;
      return !items || items.type === "string" ? "tags" : "unsupported";
    }
    case "string": {
      if (property.format === "textarea") return "textarea";
      const maxLength = property.maxLength as number | undefined;
      if (maxLength !== undefined) return maxLength > 200 ? "textarea" : "text";
      // Free text with no limit and no default of its own is prose (a prompt, a message body).
      return property.default === undefined || property.default === null ? "textarea" : "text";
    }
    default:
      return "unsupported";
  }
}

export function resolveFields(schema: JsonSchema | null | undefined): FormField[] {
  const properties = (schema?.properties ?? {}) as Record<string, JsonSchema>;
  const required = new Set((schema?.required as string[] | undefined) ?? []);

  return Object.entries(properties).map(([key, raw]) => {
    const property = unwrap(raw);
    const labels = (property["x-enum-labels"] ?? {}) as Record<string, string>;
    const options = Array.isArray(property.enum)
      ? (property.enum as unknown[]).map((value) => ({ value: String(value), label: labels[String(value)] ?? humanise(String(value)) }))
      : [];
    const items = property.items as JsonSchema | undefined;
    return {
      key,
      title: (property.title as string | undefined) ?? humanise(key),
      description: property.description as string | undefined,
      required: required.has(key),
      widget: widgetFor(property, options),
      options,
      default: property.default,
      hasDefault: "default" in property && property.default !== null,
      unit: property["x-unit"] as string | undefined,
      minimum: property.minimum as number | undefined,
      maximum: property.maximum as number | undefined,
      minLength: property.minLength as number | undefined,
      maxLength: property.maxLength as number | undefined,
      minItems: property.minItems as number | undefined,
      itemFormat: items?.format as string | undefined,
      provider: property["x-provider"] as string | undefined,
    };
  });
}

export function optionLabel(field: FormField, value: unknown): string {
  return field.options.find((option) => option.value === String(value))?.label ?? String(value);
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Format checks the form can make on its own (§17.2 "on blur"). Completeness is the server's. */
export function checkValue(field: FormField, value: unknown): string | null {
  if (isEmpty(value)) return null;
  if (typeof value === "string") {
    if (field.minLength !== undefined && value.trim().length < field.minLength) {
      return `Use at least ${field.minLength} characters.`;
    }
    if (field.maxLength !== undefined && value.length > field.maxLength) {
      return `Keep it to ${field.maxLength} characters or fewer.`;
    }
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "Enter a number.";
    if (field.minimum !== undefined && value < field.minimum) return `Use ${field.minimum} or more.`;
    if (field.maximum !== undefined && value > field.maximum) return `Use ${field.maximum} or fewer.`;
  }
  return null;
}

export function checkItem(field: FormField, item: string): string | null {
  if (field.itemFormat === "email" && !EMAIL.test(item)) return `“${item}” isn't an email address.`;
  return null;
}

function countOf(field: FormField, count: number): string {
  if (field.itemFormat === "email") return `${count} ${count === 1 ? "recipient" : "recipients"}`;
  const noun = field.title.toLowerCase();
  return `${count} ${count === 1 ? noun.replace(/s$/, "") : noun}`;
}

/**
 * The node's summary line (§15.2), in the user's words: `5 sources`, `Short · Conversational`,
 * `1 recipient · Subject: Weekly digest`. Only what the user chose — prose is never spilled onto
 * the canvas, and nothing secret is ever shown.
 */
export function summarise(configuration: Configuration | null | undefined, schema: JsonSchema | null | undefined, limit = 3): string[] {
  if (!configuration) return [];
  const parts: string[] = [];
  for (const field of resolveFields(schema)) {
    const value = configuration[field.key];
    if (isEmpty(value)) continue;
    switch (field.widget) {
      case "segmented":
      case "select":
        parts.push(optionLabel(field, value));
        break;
      case "number":
        parts.push(field.unit ? `${String(value)} ${field.unit}` : `${field.title}: ${String(value)}`);
        break;
      case "tags":
        if (Array.isArray(value)) parts.push(countOf(field, value.length));
        break;
      case "switch":
        if (value === true) parts.push(field.title);
        break;
      case "text":
        parts.push(`${field.title}: ${String(value)}`);
        break;
      default:
        break; // textarea, credential, unsupported
    }
  }
  return parts.slice(0, limit);
}

/** Required settings the user has not filled in, as the field names a person reads. */
export function missingSettings(configuration: Configuration | null | undefined, schema: JsonSchema | null | undefined): FormField[] {
  return resolveFields(schema).filter((field) => field.required && isEmpty(configuration?.[field.key]));
}
