// P-02 Handoff Lines (DESIGN-SYSTEM.md §07): parallel sine waves, each phase-shifted from the last
// so the set appears to flow. Auth hero, deck and report covers only — never inside the app shell.
export function HandoffLines({ lines = 32, className = "" }: { lines?: number; className?: string }) {
  const width = 400;
  const spacing = 8;
  const amplitude = 10;
  const wavelength = 120;

  // One period sampled every 8 px, drawn 4° further through the cycle on each successive line.
  const path = (index: number) => {
    const phase = (index * 4 * Math.PI) / 180;
    const y = 12 + index * spacing;
    const points = [];
    for (let x = 0; x <= width; x += 8) {
      points.push(`${x},${(y + Math.sin((x / wavelength) * Math.PI * 2 + phase) * amplitude).toFixed(2)}`);
    }
    return `M ${points.join(" L ")}`;
  };

  return (
    <svg
      viewBox={`0 0 ${width} ${lines * spacing + 24}`}
      preserveAspectRatio="none"
      fill="none"
      aria-hidden
      className={className}
    >
      {Array.from({ length: lines }, (_, index) => (
        <path key={index} d={path(index)} stroke="currentColor" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  );
}
