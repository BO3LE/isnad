import type { HTMLAttributes, ReactNode } from "react";

// DESIGN-SYSTEM.md §14.8 — not everything is a card; use it for real objects (a workflow, a file).
export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: "compact" | "default";
  interactive?: boolean;
  children: ReactNode;
}

export function Card({ padding = "default", interactive = false, className = "", children, ...rest }: CardProps) {
  return (
    <div
      {...rest}
      className={`rounded-md border border-border bg-surface shadow-1 ${padding === "compact" ? "p-4" : "p-6"} ${
        interactive ? "transition-shadow duration-100 ease-standard hover:shadow-2" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}
