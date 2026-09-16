import { LoaderCircle } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

// DESIGN-SYSTEM.md §14.1 — one Primary and at most one Accent (Run) per view.
export type ButtonVariant = "primary" | "accent" | "secondary" | "ghost" | "danger" | "dangerSecondary" | "link";
export type ButtonSize = "sm" | "md" | "lg";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-surface-inverse text-text-inverse hover:opacity-90",
  accent: "bg-accent text-accent-on hover:brightness-95",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-hover",
  ghost: "bg-transparent text-text hover:bg-surface-hover",
  danger: "bg-danger text-danger-on hover:opacity-90",
  dangerSecondary: "bg-surface text-status-failed-fg border border-status-failed-solid hover:bg-status-failed-bg",
  link: "bg-transparent text-interactive underline-offset-2 hover:underline",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-caption",
  md: "h-9 gap-2 px-3.5 text-body-md font-medium",
  lg: "h-11 gap-2 px-5 text-body-lg font-medium",
};

const iconSize: Record<ButtonSize, number> = { sm: 14, md: 16, lg: 20 };

// Tailwind resolves same-specificity utilities by stylesheet order, not class order, so a `px-0`
// on the variant would lose to the size's padding. The link variant drops it here instead.
const LINK_SIZES: Record<ButtonSize, string> = {
  sm: "h-7 gap-1.5 text-caption",
  md: "h-9 gap-2 text-body-md font-medium",
  lg: "h-11 gap-2 text-body-lg font-medium",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Keeps the label, swaps the leading icon for a spinner, and blocks clicks. */
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading = false, icon, className = "", children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm transition-[background-color,opacity,filter] duration-100 ease-standard active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${variant === "link" ? LINK_SIZES[size] : sizes[size]} ${className}`}
    >
      {loading ? <LoaderCircle size={iconSize[size]} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});
