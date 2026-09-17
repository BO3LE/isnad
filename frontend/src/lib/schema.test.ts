import type { AgentManifest } from "./api";
import { checkItem, checkValue, missingSettings, resolveFields, setValue, summarise, unwrap } from "./schema";
import live from "@/test/catalog.json";

// The six live catalog entries, captured from GET /agents/catalog. The renderer is tested against
// what the agents really publish, not against schemas written for the test.
const catalog = live as unknown as AgentManifest[];
const schemaOf = (name: string) => catalog.find((a) => a.name === name)!.config_schema;
const widgets = (name: string) => Object.fromEntries(resolveFields(schemaOf(name)).map((f) => [f.key, f.widget]));

describe("resolveFields — every live field gets the intended control", () => {
  it("Researcher", () => {
    expect(widgets("researcher")).toEqual({ topic: "textarea", num_sources: "number" });
    const sources = resolveFields(schemaOf("researcher")).find((f) => f.key === "num_sources")!;
    expect(sources).toMatchObject({ unit: "sources", minimum: 1, maximum: 10, default: 5, hasDefault: true });
  });

  it("Writer", () => {
    expect(widgets("writer")).toEqual({ length: "segmented", style: "select", format: "segmented" });
  });

  it("Image — the optional prompt is unwrapped from anyOf, not dropped", () => {
    expect(widgets("image")).toEqual({ prompt: "textarea", count: "number", aspect: "segmented" });
    const prompt = resolveFields(schemaOf("image")).find((f) => f.key === "prompt")!;
    expect(prompt.hasDefault).toBe(false);
    const aspect = resolveFields(schemaOf("image")).find((f) => f.key === "aspect")!;
    expect(aspect.options.map((o) => o.label)).toEqual(["Landscape 16:9", "Square 1:1"]);
  });

  it("Video", () => {
    expect(widgets("video")).toEqual({ voice: "text", resolution: "segmented" });
  });

  it("Publisher — readable platforms, and the account is never a text box", () => {
    expect(widgets("publisher")).toEqual({
      platform: "segmented",
      credential_id: "credential",
      title: "text",
      tags: "tags",
      privacy: "segmented",
    });
    const platform = resolveFields(schemaOf("publisher")).find((f) => f.key === "platform")!;
    expect(platform.options.map((o) => o.label)).toEqual(["YouTube", "Google Drive"]);
  });

  it("Email — recipients are checked as addresses", () => {
    expect(widgets("email")).toEqual({ recipients: "tags", subject: "text", body: "textarea" });
    const to = resolveFields(schemaOf("email")).find((f) => f.key === "recipients")!;
    expect(to).toMatchObject({ required: true, itemFormat: "email", minItems: 1 });
  });

  it("an unknown type degrades instead of crashing", () => {
    const fields = resolveFields({ properties: { shape: { type: "object" } } });
    expect(fields[0]?.widget).toBe("unsupported");
  });

  it("leaves a plain property alone", () => {
    expect(unwrap({ type: "string" })).toEqual({ type: "string" });
  });
});

describe("setValue — a step's settings hold only what the user chose", () => {
  it("removes a cleared field instead of storing it empty", () => {
    expect(setValue({ prompt: "A sunset", count: 2 }, "prompt", "")).toEqual({ count: 2 });
    expect(setValue({ tags: ["a"] }, "tags", [])).toEqual({});
    expect(setValue({ subject: "Hi" }, "subject", null)).toEqual({});
  });

  it("stores a real value", () => {
    expect(setValue({}, "count", 3)).toEqual({ count: 3 });
  });

  it("never mutates the configuration it was given", () => {
    const before = { prompt: "A sunset" };
    setValue(before, "prompt", "");
    expect(before).toEqual({ prompt: "A sunset" });
  });
});

describe("summarise — the node reads as labels, not raw values", () => {
  it("Researcher shows its unit and keeps the topic off the canvas", () => {
    expect(summarise({ topic: "The future of solar energy in Saudi Arabia", num_sources: 5 }, schemaOf("researcher"))).toEqual([
      "5 sources",
    ]);
  });

  it("Writer shows option labels", () => {
    expect(summarise({ length: "short", style: "conversational", format: "video_script" }, schemaOf("writer"))).toEqual([
      "Short",
      "Conversational",
      "Video script",
    ]);
  });

  it("Publisher says YouTube, not youtube", () => {
    expect(summarise({ platform: "youtube", privacy: "unlisted" }, schemaOf("publisher"))).toEqual(["YouTube", "Unlisted"]);
  });

  it("Email says who it goes to and never spills the message body", () => {
    expect(
      summarise({ recipients: ["demo@gp.local"], subject: "Weekly digest", body: "Here's the latest:" }, schemaOf("email")),
    ).toEqual(["1 recipient", "Subject: Weekly digest"]);
  });

  it("shows nothing for settings the user never chose", () => {
    expect(summarise({}, schemaOf("writer"))).toEqual([]);
  });
});

describe("missingSettings", () => {
  it("treats empty values the way /validate does", () => {
    expect(missingSettings({ recipients: [] }, schemaOf("email")).map((f) => f.key)).toEqual(["recipients"]);
    expect(missingSettings({ topic: "" }, schemaOf("researcher")).map((f) => f.key)).toEqual(["topic"]);
    expect(missingSettings({ topic: "Solar" }, schemaOf("researcher"))).toEqual([]);
  });
});

describe("checks the form can make on its own", () => {
  const fields = resolveFields(schemaOf("researcher"));
  const topic = fields.find((f) => f.key === "topic")!;
  const sources = fields.find((f) => f.key === "num_sources")!;
  const to = resolveFields(schemaOf("email")).find((f) => f.key === "recipients")!;

  it("length and range", () => {
    expect(checkValue(topic, "AI")).toBe("Use at least 3 characters.");
    expect(checkValue(topic, "Solar")).toBeNull();
    expect(checkValue(sources, 11)).toBe("Use 10 or fewer.");
    expect(checkValue(sources, 0)).toBe("Use 1 or more.");
  });

  it("email addresses", () => {
    expect(checkItem(to, "demo@gp.local")).toBeNull();
    expect(checkItem(to, "demo")).toBe("“demo” isn't an email address.");
  });
});
