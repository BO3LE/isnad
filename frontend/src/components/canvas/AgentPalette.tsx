import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useMemo, useState, type DragEvent } from "react";
import { AgentIcon } from "@/design-system/agents/AgentIcon";
import { agentFamily } from "@/design-system/agents/agentMeta";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { IconButton } from "@/design-system/components/IconButton";
import { SearchInput } from "@/design-system/components/Input";
import { Skeleton } from "@/design-system/components/Skeleton";
import { Tooltip } from "@/design-system/components/Tooltip";
import type { AgentManifest } from "@/lib/api";

// DESIGN-SYSTEM.md §15.1 — the palette renders whatever GET /agents/catalog returns, grouped by
// family. AT-12: a seventh agent appears here automatically, with no design or code change.
export const AGENT_DRAG_TYPE = "application/x-isnad-agent";

const GROUPS = [
  { family: "create" as const, label: "Create" },
  { family: "distribute" as const, label: "Distribute" },
];

export interface AgentPaletteProps {
  catalog: AgentManifest[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  /** Keyboard route into the canvas: focus an item and press Enter (§15.1). */
  onAdd: (agentType: string) => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function AgentPalette({ catalog, loading, error, onRetry, onAdd, disabled, disabledReason }: AgentPaletteProps) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const matches = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return catalog;
    return catalog.filter(
      (agent) => agent.title.toLowerCase().includes(query) || (agent.description ?? "").toLowerCase().includes(query),
    );
  }, [catalog, search]);

  function onDragStart(event: DragEvent, agentType: string) {
    event.dataTransfer.setData(AGENT_DRAG_TYPE, agentType);
    event.dataTransfer.effectAllowed = "copy";
  }

  if (collapsed) {
    return (
      <aside className="hidden w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-surface py-2 md:flex" aria-label="Agents">
        <IconButton label="Expand the agent palette" icon={<PanelLeftOpen size={16} aria-hidden />} onClick={() => setCollapsed(false)} />
        {matches.map((agent) => (
          <Tooltip key={agent.name} content={agent.title} placement="bottom">
            <button
              type="button"
              draggable={!disabled}
              onDragStart={(event) => onDragStart(event, agent.name)}
              onClick={() => !disabled && onAdd(agent.name)}
              aria-label={`Add ${agent.title}`}
              className="grid h-10 w-10 place-items-center rounded-sm hover:bg-surface-hover disabled:opacity-40"
              disabled={disabled}
            >
              <AgentIcon agentType={agent.name} icon={agent.icon} family={agent.family} />
            </button>
          </Tooltip>
        ))}
      </aside>
    );
  }

  return (
        // Hidden on phones, as in the prototype: the canvas there is for reviewing and settings.
    <aside className="hidden w-[264px] shrink-0 flex-col border-r border-border bg-surface md:flex" aria-label="Agents">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <div className="flex-1">
          <SearchInput label="Search agents" value={search} onValueChange={setSearch} placeholder="Search agents" />
        </div>
        <IconButton label="Collapse the agent palette" icon={<PanelLeftClose size={16} aria-hidden />} onClick={() => setCollapsed(true)} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {disabled && disabledReason && (
          <p className="px-1 pb-2 text-body-sm text-text-muted">{disabledReason}</p>
        )}

        {loading && (
          <div className="grid gap-2 p-1">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-14 w-full" />
            ))}
          </div>
        )}

        {error && (
          <Banner variant="error" action={<Button size="sm" onClick={onRetry}>Retry</Button>}>
            Couldn't load agents.
          </Banner>
        )}

        {!loading && !error && matches.length === 0 && (
          <p className="p-2 text-body-sm text-text-muted">No agent matches “{search.trim()}”.</p>
        )}

        {GROUPS.map(({ family, label }) => {
          const group = matches
            .filter((agent) => agentFamily(agent.name, agent.family) === family)
            .sort((a, b) => a.title.localeCompare(b.title));
          if (group.length === 0) return null;

          return (
            <section key={family} className="pb-2">
              <h2 className="px-2 pb-1 pt-2 text-overline uppercase text-text-muted">{label}</h2>
              <ul className="grid list-none gap-0.5 p-0">
                {group.map((agent) => (
                  <li key={agent.name}>
                    <button
                      type="button"
                      draggable={!disabled}
                      disabled={disabled}
                      onDragStart={(event) => onDragStart(event, agent.name)}
                      onClick={() => onAdd(agent.name)}
                      title={agent.description ?? agent.title}
                      className="flex h-14 w-full items-center gap-2.5 rounded-sm px-2 text-left hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <AgentIcon agentType={agent.name} icon={agent.icon} family={agent.family} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="truncate text-body-md font-medium text-text">{agent.title}</span>
                          {agent.requires_approval && (
                            <span aria-label="Requires approval" title="Requires approval" className="font-mono text-mono-sm text-status-approval-fg">
                              ‖
                            </span>
                          )}
                        </span>
                        <span className="block truncate text-body-sm text-text-muted">{agent.description}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </aside>
  );
}
