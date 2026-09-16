import { createContext, useContext } from "react";

// DESIGN-SYSTEM.md §14.14 — the toast contract, kept apart from the provider component.
export type ToastVariant = "info" | "success" | "warning" | "error" | "undo";

export interface ToastOptions {
  variant?: ToastVariant;
  message: string;
  action?: { label: string; onClick: () => void };
}

export const ToastContext = createContext<((options: ToastOptions) => void) | null>(null);

export function useToast(): (options: ToastOptions) => void {
  const toast = useContext(ToastContext);
  if (!toast) throw new Error("useToast must be used inside <ToastProvider>");
  return toast;
}
