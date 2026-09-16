import { CircleX } from "lucide-react";
import { useId, type ReactNode } from "react";

// DESIGN-SYSTEM.md §14.3 / §17.2 — label above, help or error below, linked with aria-describedby.
export interface FieldProps {
  label: string;
  /** Marks the field required and adds the visible asterisk. */
  required?: boolean;
  help?: ReactNode;
  error?: string | null;
  /** Receives the ids the control must carry. */
  children: (props: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
  className?: string;
}

export function Field({ label, required = false, help, error = null, children, className = "" }: FieldProps) {
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  // Only ids that are actually rendered below — an error replaces the help text, so pointing at
  // both would leave aria-describedby referencing a missing element.
  const describedBy = (error ? errorId : help ? helpId : null) ?? undefined;

  return (
    <div className={`grid gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-body-md font-medium text-text">
        {label}
        {required && (
          <>
            <span aria-hidden className="text-status-failed-fg">
              {" *"}
            </span>
            <span className="sr-only"> (required)</span>
          </>
        )}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {error ? (
        <p id={errorId} className="flex items-start gap-1.5 text-body-sm text-status-failed-fg">
          <CircleX size={14} className="mt-0.5 shrink-0" aria-hidden />
          {error}
        </p>
      ) : (
        help && (
          <p id={helpId} className="text-body-sm text-text-muted">
            {help}
          </p>
        )
      )}
    </div>
  );
}
