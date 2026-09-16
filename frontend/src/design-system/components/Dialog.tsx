import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button, type ButtonVariant } from "./Button";
import { IconButton } from "./IconButton";

// DESIGN-SYSTEM.md §14.12 — built on <dialog>, which gives focus trapping, Esc and inert background for free.
export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "confirm" | "content";
}

export function Dialog({ open, onClose, title, description, children, footer, size = "confirm" }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      className={`m-auto w-[calc(100vw-32px)] rounded-lg border border-border bg-surface p-0 text-text shadow-4 backdrop:bg-[rgb(11_11_10/0.4)] ${
        size === "confirm" ? "max-w-[440px]" : "max-w-[640px]"
      }`}
    >
      {open && (
        <div className="grid gap-4 p-6">
          <div className="flex items-start gap-4">
            <div className="grid flex-1 gap-1.5">
              <h2 id={titleId} className="text-heading-md">
                {title}
              </h2>
              {description && (
                <div id={descriptionId} className="text-body-md text-text-muted">
                  {description}
                </div>
              )}
            </div>
            <IconButton label="Close" icon={<X size={16} aria-hidden />} size="sm" onClick={onClose} />
          </div>
          {children}
          {footer && <div className="flex flex-wrap justify-end gap-2">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: ReactNode;
  /** Repeats the verb, e.g. "Delete workflow". */
  confirmLabel: string;
  cancelLabel?: string;
  confirmVariant?: ButtonVariant;
  loading?: boolean;
  children?: ReactNode;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  confirmVariant = "danger",
  loading,
  children,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          {/* Least destructive action first in the tab order. */}
          <Button onClick={onClose}>{cancelLabel}</Button>
          <Button variant={confirmVariant} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
