import { ApiError, api, endpoints } from "./api";
import type { components } from "./api-types";

// The one place that knows how signing in actually works.
//
// D-01 (Supabase Auth vs in-house) is not signed off, so the API has only POST /auth/dev-login —
// any email, no password. The screens call signIn/register below and never the API directly, so
// when D-01 lands this file changes and P-01/P-02 do not.
//
// TODO(W2, Hasan): point signIn at POST /auth/login and register at POST /auth/register.

type TokenResponse = components["schemas"]["TokenResponse"];

export type AuthMode = "dev" | "password";

/** Dev sign-in accepts any email and ignores the password; the real endpoints do not exist yet. */
export const AUTH_MODE: AuthMode = ((import.meta.env.VITE_AUTH_MODE as AuthMode | undefined) ?? "dev") satisfies AuthMode;

export interface Credentials {
  email: string;
  password: string;
}

/** DESIGN-SYSTEM.md §21 S-01: never say which of the two was wrong. */
const WRONG_CREDENTIALS = "That email and password don't match.";
const RATE_LIMITED = "Too many attempts. Try again in a minute.";
const UNREACHABLE = "Couldn't reach the server. Check your connection and try again.";

/** Turns an API failure into something the form can show, per the S-01 error table. */
export function authErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return UNREACHABLE;
  if (error.status === 401 || error.status === 400) return WRONG_CREDENTIALS;
  if (error.status === 429) return RATE_LIMITED;
  return error.message;
}

export async function signIn({ email, password }: Credentials): Promise<TokenResponse> {
  if (AUTH_MODE === "dev") return endpoints.devLogin(email);
  return api<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export async function register({ email, password }: Credentials): Promise<TokenResponse> {
  if (AUTH_MODE === "dev") return endpoints.devLogin(email);
  return api<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}

export const PASSWORD_MIN_LENGTH = 8;

/** The one rule S-01 shows before the user types, with a live check mark. */
export function meetsPasswordRules(password: string): boolean {
  return password.length >= PASSWORD_MIN_LENGTH;
}
