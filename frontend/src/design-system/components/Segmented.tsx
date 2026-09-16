import { useRef, type KeyboardEvent } from "react";

// DESIGN-SYSTEM.md §14.4 — 2–4 short, mutually exclusive options, all visible at once.
export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedProps<T extends string> {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
}

export function Segmented<T extends string>({ label, options, value, onChange, disabled, className = "" }: SegmentedProps<T>) {
  const groupRef = useRef<HTMLDivElement>(null);

  // A radio group is one tab stop; the arrow keys move (and select) inside it (§13 Keyboard).
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    const index = options.findIndex((option) => option.value === value);
    if (index < 0) return;
    event.preventDefault();
    const next = options[(index + step + options.length) % options.length];
    if (!next) return;
    onChange(next.value);
    groupRef.current?.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  }

  return (
    <div
      ref={groupRef}
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={`inline-flex h-8 items-center gap-0.5 rounded-sm bg-bg-sunken p-0.5 ${className}`}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            data-value={option.value}
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`h-7 rounded-[4px] px-3 text-body-sm transition-colors duration-100 ease-standard disabled:cursor-not-allowed disabled:opacity-40 ${
              selected ? "bg-surface font-medium text-text shadow-1" : "text-text-muted hover:text-text"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
