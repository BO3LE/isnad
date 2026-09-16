import { useId, useRef, useState, type ReactElement, type ReactNode } from "react";

// DESIGN-SYSTEM.md §14.11 — 400 ms on hover, immediate on keyboard focus, Esc dismisses.
// Never put essential information only in a tooltip.
export interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  placement?: "top" | "bottom";
  className?: string;
}

export function Tooltip({ content, children, placement = "bottom", className = "" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const timer = useRef<number>();

  function show(delay: number) {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  }

  function hide() {
    window.clearTimeout(timer.current);
    setOpen(false);
  }

  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => show(400)}
      onMouseLeave={hide}
      onFocusCapture={() => show(0)}
      onBlurCapture={hide}
      onKeyDown={(event) => event.key === "Escape" && hide()}
    >
      <span aria-describedby={open ? id : undefined} className="contents">
        {children}
      </span>
      {open && (
        <span
          role="tooltip"
          id={id}
          className={`pointer-events-none absolute left-1/2 z-tooltip w-max max-w-[240px] -translate-x-1/2 rounded-sm bg-surface-inverse px-2 py-1.5 text-caption text-text-inverse shadow-2 ${
            placement === "bottom" ? "top-[calc(100%+6px)]" : "bottom-[calc(100%+6px)]"
          }`}
        >
          {content}
        </span>
      )}
    </span>
  );
}
