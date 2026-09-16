import { Clapperboard, Image, Mail, PenLine, Puzzle, Telescope, UploadCloud, type LucideIcon } from "lucide-react";
import type { AgentManifest } from "@/lib/api";

// DESIGN-SYSTEM.md §08 — agents are identified by icon and name, never by colour. Colour means state.
export type AgentFamily = "create" | "distribute";

const ICONS: Record<string, LucideIcon> = {
  researcher: Telescope,
  writer: PenLine,
  image: Image,
  video: Clapperboard,
  publisher: UploadCloud,
  email: Mail,
};

// AT-12: a seventh agent must appear with no frontend change. An unknown type falls back to the
// manifest's own icon name, then to Puzzle — it is never a missing glyph or a crash.
const BY_MANIFEST_NAME: Record<string, LucideIcon> = {
  telescope: Telescope,
  "pen-line": PenLine,
  penline: PenLine,
  image: Image,
  clapperboard: Clapperboard,
  "upload-cloud": UploadCloud,
  uploadcloud: UploadCloud,
  mail: Mail,
};

export function agentIcon(agentType: string, manifestIcon?: string | null): LucideIcon {
  return ICONS[agentType] ?? (manifestIcon ? BY_MANIFEST_NAME[manifestIcon.toLowerCase()] : undefined) ?? Puzzle;
}

export function agentFamily(agentType: string, manifestFamily?: string | null): AgentFamily {
  if (manifestFamily === "distribute" || manifestFamily === "create") return manifestFamily;
  return agentType === "publisher" || agentType === "email" ? "distribute" : "create";
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
