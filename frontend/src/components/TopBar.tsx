import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export function Logo() {
  return (
    <svg viewBox="0 0 64 24" width="40" height="15" fill="none" aria-hidden>
      <line x1="11" y1="12" x2="27" y2="12" stroke="currentColor" strokeWidth="2" />
      <line x1="37" y1="12" x2="53" y2="12" stroke="currentColor" strokeWidth="2" />
      <circle cx="6" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <circle cx="32" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
      <circle cx="58" cy="12" r="5" fill="currentColor" />
    </svg>
  );
}

export function TopBar({ children }: { children?: ReactNode }) {
  const { email, signOut } = useAuth();
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface px-4">
      <Link to="/workflows" className="flex items-center gap-2 font-semibold text-text" aria-label="Workflows">
        <Logo />
      </Link>
      <div className="flex min-w-0 flex-1 items-center gap-3">{children}</div>
      <span className="hidden text-body-sm text-text-muted sm:inline">{email}</span>
      <button className="text-body-sm text-text-muted hover:text-text" onClick={signOut}>
        Sign out
      </button>
    </header>
  );
}
