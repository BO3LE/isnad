import { Lock, PanelLeftClose, PanelLeftOpen, Sparkles } from "lucide-react";
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
import { chainOrder, type Suggestion } from "@/lib/handover";

// DESIGN-SYSTEM.md §15.1 — the palette renders whatever GET /agents/catalog returns (AT-12).
//
// It is built for putting a chain together, not for browsing: agents are listed in the order a
// chain runs, "Suggested next" names what fits after the current step and why, and a click adds the
// agent after that step and connects it. Dragging still drops a step anywhere.
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
  /** Click or Enter: add after `after` (§15.1 keyboard route). */
  onAdd: (agentType: string) => void;
  /** Title of the step a click adds after, or null on an empty canvas. */
  after: string | null;
  suggestions: Suggestion[];
  disabled?: boolean;
  disabledReason?: string;
}

function AgentRow({
  agent,
  note,
  disabled,
  onAdd,
  onDragStart,
}: {
  agent: AgentManifest;
  note?: string;
  disabled?: boolean;
  onAdd: () => void;
  onDragStart: (event: DragEvent) => void;
}) {
  return (
    <button
      type="button"
      draggable={!disabled}
      disabled={disabled}
      onDragStart={onDragStart}
      onClick={onAdd}
      className="flex w-full min-w-0 items-start gap-2.5 rounded-sm px-2 py-2 text-left hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
    >
      <AgentIcon agentType={agent.name} icon={agent.icon} family={agent.family} className="mt-0.5" />
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-body-md font-medium text-text">{agent.title}</span>
          {agent.requires_approval && (
            <span aria-label="Waits for your approval" title="Waits for your approval" className="font-mono text-mono-sm text-status-approval-fg">
              ‖
            </span>
          )}
        </span>
        {note ? (
          <span className="text-body-sm text-status-success-fg">{note}</span>
        ) : (
          <span className="line-clamp-2 text-body-sm text-text-muted">{agent.description}</span>
        )}
      </span>
    </button>
  );
}

export function AgentPalette({ catalog, loading, error, onRetry, onAdd, after, suggestions, disabled, disabledReason }: AgentPaletteProps) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const ordered = useMemo(() => chainOrder(catalog), [catalog]);
  const query = search.trim().toLowerCase();
  const matches = useMemo(
    () =>
      query
        ? ordered.filter((agent) => agent.title.toLowerCase().includes(query) || (agent.description ?? "").toLowerCase().includes(query))
        : ordered,
    [ordered, query],
  );

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
    <aside className="hidden w-[272px] shrink-0 flex-col border-r border-border bg-surface md:flex" aria-label="Agents">
      <div className="grid gap-2 border-b border-border p-3">
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <SearchInput label="Search agents" value={search} onValueChange={setSearch} placeholder="Search agents" />
          </div>
          <IconButton label="Collapse the agent palette" icon={<PanelLeftClose size={16} aria-hidden />} onClick={() => setCollapsed(true)} />
        </div>
        {disabled ? (
          <p className="flex items-center gap-1.5 text-body-sm text-text-muted">
            <Lock size={14} aria-hidden className="shrink-0" />
            {disabledReason}
          </p>
        ) : (
          <p className="text-body-sm text-text-muted">
            {after ? (
              <>
                Click to add after <strong className="font-medium text-text">{after}</strong>, or drag onto the canvas.
              </>
            ) : (
              "Click to add a step, or drag it onto the canvas."
            )}
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
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

        {!query && !disabled && suggestions.length > 0 && (
          <section aria-labelledby="palette-suggested" className="mb-2 rounded-sm bg-bg-sunken pb-1">
            <h2 id="palette-suggested" className="flex items-center gap-1.5 px-2 pb-1 pt-2 text-overline uppercase text-text-muted">
              <Sparkles size={12} aria-hidden />
              Suggested next
            </h2>
            <ul className="grid list-none gap-0.5 p-0">
              {suggestions.map(({ agent, reason }) => (
                <li key={agent.name} className="min-w-0">
                  <AgentRow
                    agent={agent}
                    note={reason}
                    onAdd={() => onAdd(agent.name)}
                    onDragStart={(event) => onDragStart(event, agent.name)}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}

        {GROUPS.map(({ family, label }) => {
          const group = matches.filter((agent) => agentFamily(agent.name, agent.family) === family);
          if (group.length === 0) return null;
          return (
            <section key={family} className="pb-2" aria-labelledby={`palette-${family}`}>
              <h2 id={`palette-${family}`} className="px-2 pb-1 pt-2 text-overline uppercase text-text-muted">
                {label}
              </h2>
              <ul className="grid list-none gap-0.5 p-0">
                {group.map((agent) => (
                  <li key={agent.name} className="min-w-0">
                    <AgentRow
                      agent={agent}
                      disabled={disabled}
                      onAdd={() => onAdd(agent.name)}
                      onDragStart={(event) => onDragStart(event, agent.name)}
                    />
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
