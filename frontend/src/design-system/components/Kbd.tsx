import type { ReactNode } from "react";

// DESIGN-SYSTEM.md §14.23
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-grid h-5 min-w-[20px] place-items-center rounded-xs border border-border border-b-border-strong bg-bg-sunken px-1.5 font-mono text-mono-sm text-text">
      {children}
    </kbd>
  );
}
