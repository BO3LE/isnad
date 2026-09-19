import { Suspense, lazy, useMemo } from "react";
import type { LucideIcon } from "lucide-react";
import { PLACEHOLDER_GLYPH, agentFamily, agentTileClass, bundledGlyph, glyphKey } from "./agentMeta";

// DESIGN-SYSTEM.md §08 / §15.1 — the 32 px icon tile used by the palette, nodes and workflow cards.
const SIZES = { sm: "h-6 w-6 rounded-xs", md: "h-8 w-8 rounded-sm", lg: "h-10 w-10 rounded-sm" } as const;
const GLYPH = { sm: 14, md: 16, lg: 20 } as const;

// AT-12: a seventh agent publishes an icon name, and any Lucide name has to work — otherwise
// "pick your own icon" quietly means "pick one of the six already used", which is the per-agent
// hard-coding this file exists to remove, wearing a different key.
//
// The names the shipped agents use are in the bundle, so the common case costs nothing. Anything
// else resolves through Lucide's full name→loader map, which is itself imported lazily: it is
// ~1700 entries, and making every visit carry it so that a seventh agent can have its glyph would
// be the wrong trade. A new agent pays one request for the map and one for its icon, once.
const fetched = new Map<string, LucideIcon>();

function glyphFor(icon?: string | null): LucideIcon | null {
  const bundled = bundledGlyph(icon);
  if (bundled) return bundled;
  if (!icon?.trim()) return null;
  const key = glyphKey(icon);
  let component = fetched.get(key);
  if (!component) {
    component = lazy(async () => {
      const { default: loaders } = await import("lucide-react/dynamicIconImports");
      const loader = (loaders as unknown as Record<string, () => Promise<{ default: LucideIcon }>>)[key];
      // A name that is not an icon resolves to the placeholder rather than throwing at render.
      return loader ? loader() : { default: PLACEHOLDER_GLYPH };
    }) as unknown as LucideIcon;
    fetched.set(key, component);
  }
  return component;
}

export interface AgentIconProps {
  /** From the manifest, so a new agent can pick its own icon without a frontend change (AT-12). */
  icon?: string | null;
  family?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}

export function AgentIcon({ icon, family, size = "md", className = "" }: AgentIconProps) {
  const Glyph = useMemo(() => glyphFor(icon), [icon]);
  const Placeholder = PLACEHOLDER_GLYPH;
  return (
    <span aria-hidden className={`grid shrink-0 place-items-center ${SIZES[size]} ${agentTileClass(agentFamily(family))} ${className}`}>
      {Glyph ? (
        // An empty tile while a glyph arrives, never the placeholder: that one means "no agent is
        // installed for this", which would be a claim about an agent that is installed.
        <Suspense fallback={<span style={{ width: GLYPH[size], height: GLYPH[size] }} />}>
          <Glyph size={GLYPH[size]} strokeWidth={1.75} />
        </Suspense>
      ) : (
        <Placeholder size={GLYPH[size]} strokeWidth={1.75} />
      )}
    </span>
  );
}
