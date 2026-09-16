import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { Field } from "@/design-system/components/Field";
import { Input, PasswordInput } from "@/design-system/components/Input";
import { AUTH_MODE, authErrorMessage, signIn as requestSignIn } from "@/lib/auth-client";
import { useAuth } from "@/lib/auth";

// P-01 · Sign in (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §21 S-01.
export function LoginPage() {
  const [email, setEmail] = useState(AUTH_MODE === "dev" ? "demo@gp.local" : "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const signIn = useAuth((state) => state.signIn);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") ?? "/workflows";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await requestSignIn({ email, password });
      signIn(access_token, email);
      navigate(next, { replace: true });
    } catch (failure) {
      setError(authErrorMessage(failure));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back.">
      <form onSubmit={submit} noValidate className="grid gap-5">
        {/* Form-level, and never says which of the two was wrong (§21 S-01). */}
        {error && <Banner variant="error">{error}</Banner>}

        <Field label="Email">
          {({ id }) => (
            <Input
              id={id}
              type="email"
              autoComplete="email"
              inputSize="lg"
              required
              readOnly={loading}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          )}
        </Field>

        <div className="grid gap-1.5">
          <div className="flex items-baseline justify-between gap-4">
            <label htmlFor="password" className="text-body-md font-medium text-text">
              Password
            </label>
            {/* S-01 puts a "Forgot?" link here. FRONTEND-PAGES-PLAN.md P-01 marks the reset flow
                "needs clarification" and none is specified, and dev sign-in has no password to
                reset — so the slot stays empty rather than linking somewhere that does not exist.
                TODO(W2, Hasan): add it with D-01, which decides who sends the reset email. */}
          </div>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            inputSize="lg"
            required={AUTH_MODE !== "dev"}
            readOnly={loading}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {AUTH_MODE === "dev" && (
            <p className="text-body-sm text-text-muted">
              Development sign-in: any email works and the password is ignored.
            </p>
          )}
        </div>

        <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
          Sign in
        </Button>

        <p className="text-body-md text-text-muted">
          New here?{" "}
          <Link to={`/register${next === "/workflows" ? "" : `?next=${encodeURIComponent(next)}`}`} className="text-interactive hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
