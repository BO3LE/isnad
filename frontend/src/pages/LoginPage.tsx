import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "@/components/app/Logo";
import { Button } from "@/design-system/components/Button";
import { ApiError, endpoints } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// S-01 (DESIGN-SYSTEM.md §21). Development sign-in only — TODO(W2): Supabase Auth email + password.
export function LoginPage() {
  const [email, setEmail] = useState("demo@gp.local");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const signIn = useAuth((s) => s.signIn);
  const navigate = useNavigate();
  const [params] = useSearchParams();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await endpoints.devLogin(email);
      signIn(access_token, email);
      navigate(params.get("next") ?? "/workflows", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the API. Is `docker compose up` running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-full place-items-center p-6">
      <form onSubmit={submit} className="grid w-full max-w-sm gap-5 rounded-lg border border-border bg-surface p-8 shadow-2">
        <div className="flex items-center gap-2 text-text">
          <Logo />
        </div>
        <div className="grid gap-1">
          <h1 className="text-heading-xl">Sign in</h1>
          <p className="text-body-sm text-text-muted">Development sign-in — no password needed.</p>
        </div>
        <label className="grid gap-1.5">
          <span className="text-body-md font-medium">Email</span>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 rounded-sm border border-border-strong bg-surface px-3 text-body-lg text-text"
          />
        </label>
        {error && (
          <p role="alert" className="text-body-sm text-status-failed-fg">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" size="lg" loading={loading}>
          Sign in
        </Button>
      </form>
    </main>
  );
}
