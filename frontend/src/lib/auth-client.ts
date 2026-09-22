import { AuthError } from "@supabase/supabase-js";
import { ApiError, api, endpoints } from "./api";
import type { components } from "./api-types";
import { AUTH_MODE } from "./auth-mode";
import { supabase } from "./supabase";

// The one place that knows how signing in actually works.
//
// D-01 (Supabase Auth vs in-house): with VITE_AUTH_MODE=supabase this talks to Supabase Auth
// directly (see INF-06 — the API verifies Supabase's own JWTs, unchanged). With no VITE_AUTH_MODE
// set it stays on POST /auth/dev-login. The screens call signIn/register below and never the API
// or supabase-js directly, so switching modes does not touch P-01/P-02.

type TokenResponse = components["schemas"]["TokenResponse"];

export type { AuthMode } from "./auth-mode";
export { AUTH_MODE } from "./auth-mode";

export interface Credentials {
  email: string;
  password: string;
}

/** DESIGN-SYSTEM.md §21 S-01: never say which of the two was wrong. */
const WRONG_CREDENTIALS = "That email and password don't match.";
const RATE_LIMITED = "Too many attempts. Try again in a minute.";
const UNREACHABLE = "Couldn't reach the server. Check your connection and try again.";

/** Thrown by register() when the Supabase project requires the confirmation email to be clicked. */
export class EmailConfirmationRequired extends Error {
  constructor() {
    super("Check your inbox — confirm your email, then sign in.");
  }
}

/** Turns an auth failure into something the form can show, per the S-01 error table. */
export function authErrorMessage(error: unknown): string {
  if (error instanceof EmailConfirmationRequired) return error.message;
  if (error instanceof AuthError) {
    // Supabase already gives this exact message for both a bad email and a bad password.
    if (error.message === "Invalid login credentials") return WRONG_CREDENTIALS;
    if (error.status === 429) return RATE_LIMITED;
    return error.message;
  }
  if (!(error instanceof ApiError)) return UNREACHABLE;
  if (error.status === 401 || error.status === 400) return WRONG_CREDENTIALS;
  if (error.status === 429) return RATE_LIMITED;
  return error.message;
}

export async function signIn({ email, password }: Credentials): Promise<TokenResponse> {
  if (AUTH_MODE === "dev") return endpoints.devLogin(email);
  if (AUTH_MODE === "supabase") {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return { access_token: data.session.access_token, token_type: "bearer" };
  }
  return api<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export async function register({ email, password }: Credentials): Promise<TokenResponse> {
  if (AUTH_MODE === "dev") return endpoints.devLogin(email);
  if (AUTH_MODE === "supabase") {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    // "Confirm email" is on for the project: signUp succeeds but returns no session until the
    // confirmation link is clicked. FRONTEND-PAGES-PLAN.md P-02 gap #6 — wording isn't specified.
    if (!data.session) throw new EmailConfirmationRequired();
    return { access_token: data.session.access_token, token_type: "bearer" };
  }
  return api<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}

export const PASSWORD_MIN_LENGTH = 8;

/** The one rule S-01 shows before the user types, with a live check mark. */
export function meetsPasswordRules(password: string): boolean {
  return password.length >= PASSWORD_MIN_LENGTH;
}
