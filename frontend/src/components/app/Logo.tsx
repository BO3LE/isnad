// DESIGN-SYSTEM.md §03 — three nodes on a line: the first two outlined, the last filled.
export function Logo({ width = 40, className = "" }: { width?: number; className?: string }) {
  return (
    <svg viewBox="0 0 64 24" width={width} height={(width * 24) / 64} fill="none" aria-hidden className={className}>
      <line x1="11" y1="12" x2="27" y2="12" stroke="currentColor" strokeWidth="2" />
      <line x1="37" y1="12" x2="53" y2="12" stroke="currentColor" strokeWidth="2" />
      <circle cx="6" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <circle cx="32" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <circle cx="58" cy="12" r="5" fill="currentColor" />
    </svg>
  );
}
