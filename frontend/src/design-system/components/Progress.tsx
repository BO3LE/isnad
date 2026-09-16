import { LoaderCircle } from "lucide-react";

// DESIGN-SYSTEM.md §14.17
export function Spinner({ size = 16, label }: { size?: number; label?: string }) {
  return (
    <span role={label ? "status" : undefined} className="inline-flex items-center gap-2 text-text-muted">
      <LoaderCircle size={size} aria-hidden className="animate-spin" />
      {label && <span className="text-body-md">{label}</span>}
    </span>
  );
}

export interface ProgressBarProps {
  /** 0–1. Omit for an indeterminate bar. */
  value?: number;
  label: string;
  tone?: "running" | "success" | "failed" | "approval";
  className?: string;
}

export function ProgressBar({ value, label, tone = "running", className = "" }: ProgressBarProps) {
  const determinate = typeof value === "number";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={determinate ? 0 : undefined}
      aria-valuemax={determinate ? 100 : undefined}
      aria-valuenow={determinate ? Math.round(value * 100) : undefined}
      className={`h-1 overflow-hidden rounded-full bg-bg-sunken ${className}`}
    >
      <span
        className={`block h-full rounded-full bg-status-${tone}-solid ${
          determinate ? "transition-[width] duration-300 ease-standard" : "w-[30%] animate-progress-slide"
        }`}
        style={determinate ? { width: `${Math.min(100, Math.max(0, value * 100))}%` } : undefined}
      />
    </div>
  );
}
