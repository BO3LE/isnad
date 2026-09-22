import { createClient } from "@supabase/supabase-js";

// Only ever called when AUTH_MODE === "supabase" (see auth-client.ts and auth.ts). The
// placeholders let the client construct without throwing in dev/test, where these are unset —
// createClient does no network I/O until a method on it is actually called.
const url = (import.meta.env.VITE_SUPABASE_URL as string | undefined) || "https://placeholder.supabase.co";
const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined) || "placeholder-anon-key";

export const supabase = createClient(url, anonKey, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
});
