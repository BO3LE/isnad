import type { ButtonHTMLAttributes } from "react";

// DESIGN-SYSTEM.md §14.1 — one Primary and at most one Accent (Run) per view.
type Variant = "primary" | "accent" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-surface-inverse text-text-inverse hover:opacity-90",
  accent: "bg-accent text-accent-on hover:brightness-95",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-hover",
  ghost: "bg-transparent text-text hover:bg-surface-hover",
  danger: "bg-danger text-white hover:opacity-90",
};

const sizes: Record<Size, string> = {
  sm: "h-7 px-2.5 text-caption gap-1.5",
  md: "h-9 px-3.5 text-body-md font-medium gap-2",
  lg: "h-11 px-5 text-body-lg font-medium gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({ variant = "secondary", size = "md", loading = false, className = "", children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm transition-colors duration-100 ease-standard active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {children}
    </button>
  );
}
