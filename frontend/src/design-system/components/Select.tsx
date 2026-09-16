import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

// DESIGN-SYSTEM.md §14.4 — a native listbox for 5–12 options (keyboard and screen readers for free).
export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  options: SelectOption[];
  invalid?: boolean;
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { options, invalid, placeholder, className = "", ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select
        {...rest}
        ref={ref}
        aria-invalid={invalid || undefined}
        className={`h-9 w-full appearance-none rounded-sm border bg-surface pl-3 pr-9 text-body-md text-text disabled:cursor-not-allowed disabled:bg-bg-sunken ${
          invalid ? "border-status-failed-solid" : "border-border-strong hover:border-border-hover focus:border-focus"
        } ${className}`}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={16}
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
      />
    </div>
  );
});
