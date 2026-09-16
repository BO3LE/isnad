import { CircleX, Hand, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

// DESIGN-SYSTEM.md §14.15 — sits at the top of the content column, full width, with an optional action.
export type BannerVariant = "info" | "warning" | "error" | "approval" | "neutral";

const STYLES: Record<BannerVariant, { box: string; icon: typeof Info | null }> = {
  info: { box: "bg-status-running-bg border-status-running-solid text-text", icon: Info },
  warning: { box: "bg-status-retrying-bg border-status-retrying-solid text-text", icon: TriangleAlert },
  error: { box: "bg-status-failed-bg border-status-failed-solid text-text", icon: CircleX },
  approval: { box: "bg-status-approval-bg border-status-approval-solid text-text", icon: Hand },
  neutral: { box: "bg-bg-sunken border-border-strong text-text", icon: null },
};

export interface BannerProps {
  variant?: BannerVariant;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function Banner({ variant = "info", children, action, className = "" }: BannerProps) {
  const { box, icon: Icon } = STYLES[variant];
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={`flex flex-wrap items-center gap-3 rounded-sm border-l-[3px] px-4 py-3 text-body-md ${box} ${className}`}
    >
      {Icon && <Icon size={16} aria-hidden className="shrink-0" />}
      <div className="flex-1">{children}</div>
      {action}
    </div>
  );
}
