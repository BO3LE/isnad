import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

// DESIGN-SYSTEM.md §14.2 — always has an accessible label; pair with a Tooltip showing the same text.
type Variant = "ghost" | "secondary";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  ghost: "bg-transparent text-text hover:bg-surface-hover",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-hover",
};

const sizes: Record<Size, string> = { sm: "h-7 w-7", md: "h-9 w-9", lg: "h-11 w-11" };

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  label: string;
  icon: ReactNode;
  variant?: Variant;
  size?: Size;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, variant = "ghost", size = "md", className = "", type = "button", ...rest },
  ref,
) {
  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      aria-label={label}
      className={`inline-grid place-items-center rounded-sm transition-colors duration-100 ease-standard disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {icon}
    </button>
  );
});
