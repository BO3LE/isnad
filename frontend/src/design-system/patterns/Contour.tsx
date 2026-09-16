// P-06 Contour (DESIGN-SYSTEM.md §07): nested closed curves — "space waiting to be filled".
// 1 px strokes in currentColor; used in empty states only, never next to real data or in error states.
export function Contour({ className = "" }: { className?: string }) {
  const rings = [0, 1, 2, 3, 4, 5];
  return (
    <svg viewBox="0 0 160 128" fill="none" aria-hidden className={className}>
      {rings.map((ring) => {
        const inset = ring * 9;
        return (
          <path
            key={ring}
            d={`M ${30 + inset} ${20 + inset * 0.7}
                C ${86 - inset * 0.2} ${6 + inset}, ${140 - inset} ${26 + inset * 0.5}, ${138 - inset} ${64}
                C ${136 - inset} ${104 - inset * 0.6}, ${96 + inset * 0.2} ${120 - inset * 0.7}, ${64 + inset * 0.4} ${116 - inset * 0.6}
                C ${30 + inset * 0.6} ${112 - inset * 0.5}, ${14 + inset} ${92 - inset * 0.4}, ${18 + inset} ${62}
                C ${21 + inset} ${38 + inset * 0.4}, ${22 + inset} ${26 + inset * 0.6}, ${30 + inset} ${20 + inset * 0.7} Z`}
            stroke="currentColor"
            strokeWidth="1"
            opacity={0.25 + ring * 0.1}
          />
        );
      })}
    </svg>
  );
}
