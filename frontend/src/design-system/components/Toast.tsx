import { CircleCheck, CircleX, Info, TriangleAlert, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { IconButton } from "./IconButton";
import { ToastContext, type ToastOptions, type ToastVariant } from "./toast-context";

// DESIGN-SYSTEM.md §14.14 — max 3 stacked, errors stay until dismissed, timers pause on hover or focus.
export type { ToastOptions, ToastVariant };

interface Toast extends ToastOptions {
  id: number;
  variant: ToastVariant;
}

const DURATIONS: Record<ToastVariant, number> = { info: 5000, success: 5000, warning: 8000, error: 0, undo: 6000 };

const ICONS: Record<ToastVariant, typeof Info> = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  error: CircleX,
  undo: Undo2,
};

const TONES: Record<ToastVariant, string> = {
  info: "text-text",
  success: "text-status-success-fg",
  warning: "text-status-retrying-fg",
  error: "text-status-failed-fg",
  undo: "text-text",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((current) => current.filter((toast) => toast.id !== id)), []);

  const push = useCallback((options: ToastOptions) => {
    const toast: Toast = { ...options, id: nextId.current++, variant: options.variant ?? "info" };
    setToasts((current) => [...current.slice(-2), toast]);
  }, []);

  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-6 z-toast grid justify-items-center gap-2 sm:left-auto sm:right-6 sm:justify-items-end">
        {toasts.map((toast) => (
          <ToastRow key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastRow({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const [paused, setPaused] = useState(false);
  const duration = DURATIONS[toast.variant];

  useEffect(() => {
    if (duration === 0 || paused) return;
    const timer = window.setTimeout(onDismiss, duration);
    return () => window.clearTimeout(timer);
  }, [duration, paused, onDismiss]);

  const Icon = ICONS[toast.variant];
  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
      className="pointer-events-auto flex w-full max-w-[360px] items-start gap-3 rounded-md border border-border bg-surface-raised p-3 shadow-4"
    >
      <Icon size={16} aria-hidden className={`mt-0.5 shrink-0 ${TONES[toast.variant]}`} />
      <p className="flex-1 text-body-md text-text">{toast.message}</p>
      {toast.action && (
        <button
          type="button"
          onClick={() => {
            toast.action?.onClick();
            onDismiss();
          }}
          className="shrink-0 text-body-md font-medium text-interactive hover:underline"
        >
          {toast.action.label}
        </button>
      )}
      <IconButton label="Dismiss" size="sm" icon={<X size={14} aria-hidden />} onClick={onDismiss} />
    </div>
  );
}
