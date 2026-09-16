import type { ReactNode } from "react";
import { Contour } from "../patterns/Contour";

// DESIGN-SYSTEM.md §14.19 — title, one line of body, and the action that fills the space.
export interface EmptyStateProps {
  title: string;
  body?: ReactNode;
  actions?: ReactNode;
  /** P-06 Contour art (DESIGN-SYSTEM.md §07). Off for error states, which must feel concrete. */
  art?: boolean;
  className?: string;
}

export function EmptyState({ title, body, actions, art = true, className = "" }: EmptyStateProps) {
  return (
    <div className={`grid justify-items-center gap-4 px-6 py-12 text-center ${className}`}>
      {art && <Contour className="h-32 w-40 text-border-strong" />}
      <div className="grid gap-1.5">
        <h2 className="text-heading-lg text-text">{title}</h2>
        {body && <p className="mx-auto max-w-[44ch] text-body-md text-text-muted">{body}</p>}
      </div>
      {actions && <div className="flex flex-wrap justify-center gap-3">{actions}</div>}
    </div>
  );
}
