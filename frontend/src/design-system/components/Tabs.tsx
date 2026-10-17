import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { slug } from "./tab-panel";

// DESIGN-SYSTEM.md §14.9 — arrow keys move between tabs (roving tabindex).
//
// A tab that controls nothing is only half a tab: a screen reader announces "tab, 1 of 2" and then
// has no way to reach what it selected, and nothing tells the reader the panel below belongs to it.
// So each tab carries an id and `aria-controls`, and `tabPanel()` hands the matching attributes to
// whoever renders the panel — the pairing is easy to get subtly wrong by hand.
//
// Only the selected panel is rendered, so an unselected tab's `aria-controls` points at an id that
// is not in the document. That is deliberate and widely tolerated: the alternative is rendering
// every panel and hiding all but one, which costs more than it buys here. Pass the same string to
// `Tabs` and to `tabPanel` — a shared constant, not two literals — or the panel silently dangles.
export interface TabItem {
  id: string;
  label: string;
  badge?: ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  label: string;
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
  /**
   * Namespace for the generated ids. Needed when two tablists share a page — the drawer shows a
   * step's panels and, inside one of them, the outputs that step made.
   */
  idPrefix?: string;
}

export function Tabs({ label, tabs, value, onChange, className = "", idPrefix }: TabsProps) {
  const prefix = slug(idPrefix ?? label);
  const listRef = useRef<HTMLDivElement>(null);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const enabled = tabs.filter((tab) => !tab.disabled);
    const index = enabled.findIndex((tab) => tab.id === value);
    if (index < 0) return;
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    const next = enabled[(index + step + enabled.length) % enabled.length];
    if (!next) return;
    onChange(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-tab-id="${next.id}"]`)?.focus();
  }

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={`flex gap-4 border-b border-border ${className}`}
    >
      {tabs.map((tab) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            id={`${prefix}-tab-${tab.id}`}
            type="button"
            role="tab"
            data-tab-id={tab.id}
            aria-controls={`${prefix}-panel-${tab.id}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={tab.disabled}
            onClick={() => onChange(tab.id)}
            className={`-mb-px flex h-10 items-center gap-2 border-b-2 text-body-md font-medium transition-colors duration-100 ease-standard disabled:cursor-not-allowed disabled:opacity-40 ${
              selected ? "border-text text-text" : "border-transparent text-text-muted hover:text-text"
            }`}
          >
            {tab.label}
            {tab.badge}
          </button>
        );
      })}
    </div>
  );
}
