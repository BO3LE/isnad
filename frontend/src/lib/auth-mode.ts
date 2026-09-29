// Split out from auth-client.ts so auth.ts can read the mode too, without the two modules
// importing each other (auth-client.ts -> api.ts -> auth.ts would otherwise cycle back here).
export type AuthMode = "dev" | "password" | "supabase";

/** Dev sign-in accepts any email and ignores the password; "supabase" talks to Supabase Auth directly. */
export const AUTH_MODE: AuthMode = ((import.meta.env.VITE_AUTH_MODE as AuthMode | undefined) ?? "dev") satisfies AuthMode;
