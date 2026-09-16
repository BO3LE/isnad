// DESIGN-SYSTEM.md §14.5 — instant settings: the value applies immediately, there is no Save.
export interface SwitchProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  /** Shown instead of the label when the control sits in a row that already has one. */
  hideLabel?: boolean;
  description?: string;
  className?: string;
}

export function Switch({ label, checked, onChange, disabled, hideLabel, description, className = "" }: SwitchProps) {
  const control = (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={hideLabel ? label : undefined}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors duration-100 ease-standard disabled:cursor-not-allowed disabled:opacity-40 ${
        checked ? "bg-surface-inverse" : "bg-border-strong"
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-0.5 h-4 w-4 rounded-full transition-[left] duration-100 ease-standard ${
          checked ? "left-[18px] bg-surface dark:bg-accent" : "left-0.5 bg-surface"
        }`}
      />
    </button>
  );

  if (hideLabel) return <span className={className}>{control}</span>;

  return (
    <label className={`flex items-start gap-3 ${disabled ? "opacity-40" : ""} ${className}`}>
      {control}
      <span className="grid gap-0.5">
        <span className="text-body-md text-text">{label}</span>
        {description && <span className="text-body-sm text-text-muted">{description}</span>}
      </span>
    </label>
  );
}
