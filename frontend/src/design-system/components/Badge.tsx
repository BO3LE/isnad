import type { ReactNode } from "react";

// DESIGN-SYSTEM.md §14.7 — meta badges ("✦ Generated", "Mock") and count badges. Status uses StatusChip.
export interface BadgeProps {
  children: ReactNode;
  tone?: "neutral" | "generated" | "count" | "danger";
  className?: string;
}

const tones = {
  neutral: "bg-bg-sunken text-text-muted",
  generated: "bg-bg-sunken text-accent-text",
  count: "bg-surface-inverse text-text-inverse",
  danger: "bg-status-failed-bg text-status-failed-fg",
} as const;

export function Badge({ children, tone = "neutral", className = "" }: BadgeProps) {
  const pill = tone === "count" ? "min-w-[18px] justify-center rounded-full px-1.5" : "rounded-xs px-1.5";
  return (
    <span className={`inline-flex h-5 w-fit shrink-0 items-center gap-1 justify-self-start text-caption ${pill} ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}
