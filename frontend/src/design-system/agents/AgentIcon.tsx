import { agentFamily, agentIcon, agentTileClass } from "./agentMeta";

// DESIGN-SYSTEM.md §08 / §15.1 — the 32 px icon tile used by the palette, nodes and workflow cards.
const SIZES = { sm: "h-6 w-6 rounded-xs", md: "h-8 w-8 rounded-sm", lg: "h-10 w-10 rounded-sm" } as const;
const GLYPH = { sm: 14, md: 16, lg: 20 } as const;

export interface AgentIconProps {
  agentType: string;
  /** From the manifest, so a new agent can pick its own icon without a frontend change (AT-12). */
  icon?: string | null;
  family?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}

export function AgentIcon({ agentType, icon, family, size = "md", className = "" }: AgentIconProps) {
  const Glyph = agentIcon(agentType, icon);
  return (
    <span aria-hidden className={`grid shrink-0 place-items-center ${SIZES[size]} ${agentTileClass(agentFamily(agentType, family))} ${className}`}>
      <Glyph size={GLYPH[size]} strokeWidth={1.75} />
    </span>
  );
}
