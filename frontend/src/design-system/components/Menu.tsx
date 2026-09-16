import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

// DESIGN-SYSTEM.md §14.10 — destructive items last, after a divider.
export interface MenuItem {
  id: string;
  label: string;
  icon?: ReactNode;
  shortcut?: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** Draws a divider above this item. */
  separated?: boolean;
}

export interface MenuProps {
  /** Rendered as the trigger; it receives the props the menu button needs. */
  trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu" }) => ReactNode;
  items: MenuItem[];
  align?: "left" | "right";
  className?: string;
}

export function Menu({ trigger, items, align = "right", className = "" }: MenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLButtonElement>("[data-menu-item]:not(:disabled)")?.focus();

    function onPointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      containerRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const options = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("[data-menu-item]:not(:disabled)") ?? []);
    const index = options.indexOf(document.activeElement as HTMLButtonElement);
    const next = options[(index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length];
    next?.focus();
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {trigger({ onClick: () => setOpen((value) => !value), "aria-expanded": open, "aria-haspopup": "menu" })}
      {open && (
        <div
          ref={menuRef}
          role="menu"
          onKeyDown={onKeyDown}
          className={`absolute z-dropdown mt-1 min-w-[200px] rounded-md border border-border bg-surface-raised p-1 shadow-2 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item) => (
            <div key={item.id}>
              {item.separated && <div role="separator" className="my-1 h-px bg-border" />}
              <button
                type="button"
                role="menuitem"
                data-menu-item
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
                className={`flex h-8 w-full items-center gap-2 rounded-xs px-2 text-left text-body-md disabled:cursor-not-allowed disabled:opacity-40 ${
                  item.danger ? "text-status-failed-fg hover:bg-status-failed-bg" : "text-text hover:bg-surface-hover"
                }`}
              >
                {item.icon}
                <span className="flex-1 truncate">{item.label}</span>
                {item.shortcut && <span className="font-mono text-mono-sm text-text-subtle">{item.shortcut}</span>}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
