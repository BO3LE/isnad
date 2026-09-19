import { Clapperboard, Image, Mail, PenLine, Puzzle, Telescope, UploadCloud, type LucideIcon } from "lucide-react";
import type { AgentManifest } from "@/lib/api";

// DESIGN-SYSTEM.md §08 — agents are identified by icon and name, never by colour. Colour means state.
export type AgentFamily = "create" | "distribute";

// AT-12: nothing here may know which agent is which. These functions are not given the agent's
// type, so they cannot consult it — an agent's look comes from its own manifest or not at all.
// The table below is keyed by *icon name*, the way a manifest publishes it, not by agent.
const GLYPHS: Record<string, LucideIcon> = {
  telescope: Telescope,
  "pen-line": PenLine,
  image: Image,
  clapperboard: Clapperboard,
  "cloud-upload": UploadCloud,
  "upload-cloud": UploadCloud,
  mail: Mail,
};

/** Manifests are written by hand, so accept the spellings a person might reasonably use. */
function glyphKey(name: string): string {
  return name.trim().toLowerCase().replace(/[\s_]+/g, "-");
}

/** The glyph a manifest asked for, or a neutral placeholder — never a blank space or a crash. */
export function agentIcon(manifestIcon?: string | null): LucideIcon {
  return (manifestIcon ? GLYPHS[glyphKey(manifestIcon)] : undefined) ?? Puzzle;
}

/** What the manifest says it is. An agent that does not say is treated as one that creates. */
export function agentFamily(manifestFamily?: string | null): AgentFamily {
  return manifestFamily === "distribute" ? "distribute" : "create";
}

/**
 * Distribute agents send content out of the platform, so they carry the heavier Ink tile (§08).
 *
 * That pairing is fixed in both themes — it is a brand mark. Using --color-surface-inverse here
 * looked right in light and inverted in dark, putting Volt on Paper at 1.1:1. The Create tile is a
 * plain neutral surface, so it does follow the theme.
 */
export function agentTileClass(family: AgentFamily): string {
  return family === "distribute" ? "bg-agent-distribute text-agent-distribute-fg" : "bg-bg-sunken text-text";
}

export interface AgentLike {
  name: string;
  title: string;
  icon?: string | null;
  family?: string | null;
}

/** Title for an agent type, falling back to the raw type so an unknown agent still reads sensibly. */
export function agentTitle(agentType: string, catalog?: AgentManifest[]): string {
  return catalog?.find((a) => a.name === agentType)?.title ?? agentType;
}

/** The manifest for a step's agent type, so a caller can hand on what the agent published. */
export function manifestFor(agentType: string, catalog?: AgentManifest[]): AgentManifest | undefined {
  return catalog?.find((a) => a.name === agentType);
}
