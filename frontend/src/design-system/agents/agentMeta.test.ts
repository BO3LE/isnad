import { Mail, Puzzle, Telescope } from "lucide-react";
import { agentFamily, agentIcon, agentTileClass } from "./agentMeta";

describe("agent icons (§08)", () => {
  it("maps the six built-in agents", () => {
    expect(agentIcon("researcher")).toBe(Telescope);
    expect(agentIcon("email")).toBe(Mail);
  });

  // AT-12: a seventh agent must appear with no frontend edit at all.
  describe("an agent the frontend has never heard of", () => {
    it("falls back to a neutral icon rather than breaking", () => {
      expect(agentIcon("translator")).toBe(Puzzle);
    });

    it("uses the icon its manifest names, when that names a Lucide icon we ship", () => {
      expect(agentIcon("scout", "telescope")).toBe(Telescope);
      expect(agentIcon("scout", "Telescope")).toBe(Telescope);
    });

    it("still falls back when the manifest names an icon we do not have", () => {
      expect(agentIcon("scout", "not-a-real-icon")).toBe(Puzzle);
    });

    it("defaults to the Create family, and honours the manifest when it says otherwise", () => {
      expect(agentFamily("translator")).toBe("create");
      expect(agentFamily("broadcaster", "distribute")).toBe("distribute");
      expect(agentFamily("broadcaster", "nonsense")).toBe("create");
    });
  });

  it("puts the built-in distribute agents in the distribute family", () => {
    expect(agentFamily("publisher")).toBe("distribute");
    expect(agentFamily("email")).toBe("distribute");
    expect(agentFamily("writer")).toBe("create");
  });

  // The Ink-tile/Volt-icon pairing is a brand mark, so it must NOT be built from a theme-flipping
  // token: surface-inverse became Paper in dark and put Volt on white at 1.1:1.
  it("builds the distribute tile from theme-independent tokens", () => {
    const distribute = agentTileClass("distribute");
    expect(distribute).toContain("bg-agent-distribute");
    expect(distribute).not.toContain("surface-inverse");
    expect(agentTileClass("create")).toContain("bg-bg-sunken");
  });
});
