// P-05 Chain Rule (DESIGN-SYSTEM.md §07): a 6 px outlined circle every 40 px, taken straight from
// the logo. A section boundary — never a table row divider or a list separator.
export function ChainRule({ links = 4, className = "" }: { links?: number; className?: string }) {
  const step = 46;
  const width = links * step;

  return (
    <svg viewBox={`0 0 ${width} 12`} fill="none" aria-hidden className={className}>
      {Array.from({ length: links }, (_, index) => {
        const cx = 6 + index * step;
        return (
          <g key={index}>
            <circle cx={cx} cy="6" r="3" stroke="currentColor" strokeWidth="1" />
            {index < links - 1 && <line x1={cx + 5} y1="6" x2={cx + step - 5} y2="6" stroke="currentColor" strokeWidth="1" />}
          </g>
        );
      })}
    </svg>
  );
}
