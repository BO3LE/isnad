// DESIGN-SYSTEM.md §14.18 — mirrors the real layout so nothing jumps when data arrives.
export interface SkeletonProps {
  className?: string;
  /** Screen-reader text for the first skeleton in a group. */
  label?: string;
}

export function Skeleton({ className = "h-4 w-full", label }: SkeletonProps) {
  return (
    <span
      aria-hidden={label ? undefined : true}
      role={label ? "status" : undefined}
      className={`block animate-pulse rounded-xs bg-bg-sunken ${className}`}
    >
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

export function SkeletonCard() {
  return (
    <div className="grid gap-3 rounded-md border border-border bg-surface p-5 shadow-1">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-5 w-24" />
    </div>
  );
}
