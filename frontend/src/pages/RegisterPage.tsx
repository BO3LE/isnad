import { Check } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Banner } from "@/design-system/components/Banner";
import { Button } from "@/design-system/components/Button";
import { Field } from "@/design-system/components/Field";
import { Input, PasswordInput } from "@/design-system/components/Input";
import { AUTH_MODE, PASSWORD_MIN_LENGTH, authErrorMessage, meetsPasswordRules, register } from "@/lib/auth-client";
import { useAuth } from "@/lib/auth";

// P-02 · Create account (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §21 S-01.
export function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const signIn = useAuth((state) => state.signIn);
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const passwordOk = meetsPasswordRules(password);
  const confirmMismatch = confirm.length > 0 && confirm !== password;

  // Field errors appear on submit, not while the user is still typing (§17.2 validation timing).
  const passwordError = submitted && !passwordOk ? `Use at least ${PASSWORD_MIN_LENGTH} characters.` : null;
  const confirmError = submitted && confirm !== password ? "Both passwords must match." : confirmMismatch ? "Both passwords must match." : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!passwordOk || confirm !== password) return;

    setLoading(true);
    try {
      const { access_token } = await register({ email, password });
      signIn(access_token, email);
      navigate(params.get("next") ?? "/workflows", { replace: true });
    } catch (failure) {
      setError(authErrorMessage(failure));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Create account" subtitle="Build your first chain in a couple of minutes.">
      <form onSubmit={submit} noValidate className="grid gap-5">
        {error && <Banner variant="error">{error}</Banner>}

        <Field label="Email" required>
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

        <Field label="Password" required error={passwordError} help={<PasswordRule met={passwordOk} />}>
          {({ id, describedBy, invalid }) => (
            <PasswordInput
              id={id}
              aria-describedby={describedBy}
              invalid={invalid}
              autoComplete="new-password"
              inputSize="lg"
              required
              readOnly={loading}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          )}
        </Field>

        <Field label="Confirm password" required error={confirmError}>
          {({ id, describedBy, invalid }) => (
            <PasswordInput
              id={id}
              aria-describedby={describedBy}
              invalid={invalid}
              autoComplete="new-password"
              inputSize="lg"
              required
              readOnly={loading}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          )}
        </Field>

        {AUTH_MODE === "dev" && (
          <p className="text-body-sm text-text-muted">
            Development sign-in: this creates a local account from the email alone. The password is not stored yet.
          </p>
        )}

        <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full">
          Create account
        </Button>

        <p className="text-body-md text-text-muted">
          Already have an account?{" "}
          <Link to="/login" className="text-interactive hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}

/** The single rule from S-01, shown before the user types and check-marked once it is met. */
function PasswordRule({ met }: { met: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 ${met ? "text-status-success-fg" : "text-text-muted"}`}>
      <Check size={14} aria-hidden className={met ? "" : "opacity-30"} />
      At least {PASSWORD_MIN_LENGTH} characters
      <span className="sr-only">{met ? " — met" : " — not met yet"}</span>
    </span>
  );
}
