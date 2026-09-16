import { Search, X } from "lucide-react";
import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

// DESIGN-SYSTEM.md §14.3 — 36 px tall (md), 1.5 px focus border plus the focus ring.
const base =
  "w-full rounded-sm border bg-surface px-3 text-body-md text-text placeholder:text-text-subtle " +
  "transition-colors duration-100 ease-standard " +
  "disabled:cursor-not-allowed disabled:border-border disabled:bg-bg-sunken disabled:text-text-subtle " +
  "read-only:border-transparent read-only:bg-bg-sunken";

// §14.3 asks for a 1.5 px edge on focus and on error. Growing the border would reflow the text by
// half a pixel, so the extra half sits in an inset shadow instead and the box never moves.
const RING_FOCUS = "focus:shadow-[inset_0_0_0_0.5px_var(--color-focus)]";
const RING_ERROR = "shadow-[inset_0_0_0_0.5px_var(--status-failed-solid)]";

const borders = (invalid?: boolean) =>
  invalid
    ? `border-status-failed-solid focus:border-status-failed-solid ${RING_ERROR}`
    : `border-border-strong hover:border-border-hover focus:border-focus ${RING_FOCUS}`;

export type InputSize = "md" | "lg";
const heights: Record<InputSize, string> = { md: "h-9", lg: "h-11 text-body-lg" };

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  invalid?: boolean;
  inputSize?: InputSize;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, inputSize = "md", className = "", ...rest },
  ref,
) {
  return (
    <input
      {...rest}
      ref={ref}
      aria-invalid={invalid || undefined}
      className={`${base} ${borders(invalid)} ${heights[inputSize]} ${className}`}
    />
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, rows = 3, className = "", ...rest },
  ref,
) {
  return (
    <textarea
      {...rest}
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={`${base} ${borders(invalid)} resize-y py-2 leading-[21px] ${className}`}
    />
  );
});

export interface NumberInputProps extends Omit<InputProps, "type"> {
  unit?: string;
}

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(function NumberInput(
  { unit, className = "", ...rest },
  ref,
) {
  return (
    <div className="relative">
      <Input {...rest} ref={ref} type="number" className={`font-mono tabular-nums ${unit ? "pr-16" : ""} ${className}`} />
      {unit && (
        <span className="pointer-events-none absolute inset-y-0 right-3 grid place-items-center text-body-sm text-text-muted">
          {unit}
        </span>
      )}
    </div>
  );
});

export interface SearchInputProps extends Omit<InputProps, "type" | "value" | "onChange"> {
  value: string;
  onValueChange: (value: string) => void;
  /** Accessible label — search fields usually have a placeholder only. */
  label: string;
}

export function SearchInput({ value, onValueChange, label, className = "", ...rest }: SearchInputProps) {
  return (
    <div className={`relative ${className}`}>
      <Search size={16} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-subtle" />
      <Input
        {...rest}
        type="search"
        aria-label={label}
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        className="px-9 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          onClick={() => onValueChange("")}
          aria-label="Clear search"
          className="absolute right-1.5 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-xs text-text-muted hover:bg-surface-hover hover:text-text"
        >
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}
