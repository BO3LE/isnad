import dynamicIconImports from "lucide-react/dynamicIconImports";
import { Clapperboard, Mail, Telescope, UploadCloud } from "lucide-react";
import { agentFamily, agentTileClass, agentTitle, bundledGlyph, glyphKey, manifestFor } from "./agentMeta";
import catalog from "@/test/catalog.json";
import type { AgentManifest } from "@/lib/api";

const agents = catalog as unknown as AgentManifest[];

describe("an agent's glyph", () => {
  it("uses the glyph the manifest asked for", () => {
    expect(bundledGlyph("telescope")).toBe(Telescope);
    expect(bundledGlyph("clapperboard")).toBe(Clapperboard);
  });

  it("forgives the spellings a manifest might be written with", () => {
    expect(bundledGlyph("Telescope")).toBe(Telescope);
    expect(bundledGlyph(" cloud_upload ")).toBe(UploadCloud);
  });

  it("draws every agent in the live catalog from its own manifest, out of the bundle", () => {
    // These are drawn constantly, so they must not cost a request.
    for (const agent of agents) expect(bundledGlyph(agent.icon)).toBeDefined();
    expect(bundledGlyph(agents.find((a) => a.name === "publisher")!.icon)).toBe(UploadCloud);
    expect(bundledGlyph(agents.find((a) => a.name === "email")!.icon)).toBe(Mail);
  });

  it("can fetch any Lucide name, not only the ones the six agents happen to use", () => {
    // AT-12: otherwise "an agent picks its own icon" would mean "picks one already picked" — the
    // same per-agent hard-coding under a different key.
    for (const name of ["languages", "database", "bot", "file-spreadsheet", "megaphone"]) {
      expect(bundledGlyph(name)).toBeUndefined();
      expect(dynamicIconImports[glyphKey(name) as keyof typeof dynamicIconImports]).toBeTypeOf("function");
    }
  });

  it("has nothing to draw for a name that is not an icon", () => {
    expect(bundledGlyph("not-a-real-icon")).toBeUndefined();
    expect(dynamicIconImports[glyphKey("not-a-real-icon") as keyof typeof dynamicIconImports]).toBeUndefined();
    expect(bundledGlyph(null)).toBeUndefined();
  });
});

describe("agentFamily", () => {
  it("takes the manifest's word", () => {
    expect(agentFamily("distribute")).toBe("distribute");
    expect(agentFamily("create")).toBe("create");
  });

  it("treats an agent that does not say as one that creates", () => {
    expect(agentFamily(null)).toBe("create");
    expect(agentFamily("nonsense")).toBe("create");
  });

  it("reads every family from the catalog, not from the agent's name", () => {
    expect(agentFamily(agents.find((a) => a.name === "publisher")!.family)).toBe("distribute");
    expect(agentFamily(agents.find((a) => a.name === "email")!.family)).toBe("distribute");
    expect(agentFamily(agents.find((a) => a.name === "writer")!.family)).toBe("create");
  });
});

describe("the agent tile", () => {
  it("gives distribute agents the heavier tile", () => {
    expect(agentTileClass("distribute")).toContain("bg-agent-distribute");
    expect(agentTileClass("create")).toContain("bg-bg-sunken");
  });
});

describe("looking an agent up", () => {
  it("finds a manifest by type and survives one that is missing", () => {
    expect(manifestFor("writer", agents)?.title).toBe("Writer");
    expect(manifestFor("translator", agents)).toBeUndefined();
    expect(manifestFor("writer", undefined)).toBeUndefined();
  });

  it("falls back to the raw type so an unknown agent still reads sensibly", () => {
    expect(agentTitle("writer", agents)).toBe("Writer");
    expect(agentTitle("translator", agents)).toBe("translator");
  });
});
