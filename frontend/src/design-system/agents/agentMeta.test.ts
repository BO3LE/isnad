import { Clapperboard, Mail, Puzzle, Telescope, UploadCloud } from "lucide-react";
import { agentFamily, agentIcon, agentTileClass, agentTitle, manifestFor } from "./agentMeta";
import catalog from "@/test/catalog.json";
import type { AgentManifest } from "@/lib/api";

const agents = catalog as unknown as AgentManifest[];

describe("agentIcon", () => {
  it("uses the glyph the manifest asked for", () => {
    expect(agentIcon("telescope")).toBe(Telescope);
    expect(agentIcon("clapperboard")).toBe(Clapperboard);
  });

  it("forgives the spellings a manifest might be written with", () => {
    expect(agentIcon("Telescope")).toBe(Telescope);
    expect(agentIcon(" cloud_upload ")).toBe(UploadCloud);
  });

  it("gives an unknown or absent icon a placeholder rather than a blank", () => {
    expect(agentIcon("not-a-real-icon")).toBe(Puzzle);
    expect(agentIcon(null)).toBe(Puzzle);
    expect(agentIcon(undefined)).toBe(Puzzle);
  });

  it("draws every agent in the live catalog from its own manifest", () => {
    // AT-12: the six are not special-cased anywhere, so each must resolve through its manifest
    // alone. A seventh agent that publishes a known icon name gets it the same way.
    for (const agent of agents) expect(agentIcon(agent.icon)).not.toBe(Puzzle);
    expect(agentIcon(agents.find((a) => a.name === "publisher")!.icon)).toBe(UploadCloud);
    expect(agentIcon(agents.find((a) => a.name === "email")!.icon)).toBe(Mail);
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
