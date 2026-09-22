import { create } from "zustand";
import { persist } from "zustand/middleware";
import { AUTH_MODE } from "./auth-mode";
import { supabase } from "./supabase";

interface AuthState {
  token: string | null;
  email: string | null;
  /** True once the initial session is known. Only ever false while Supabase's stored session is
   *  still loading — dev/password mode has nothing to wait for, so it starts true. Read this
   *  before redirecting a signed-out-looking user, or a refresh briefly bounces them to /login. */
  hydrated: boolean;
  signIn: (token: string, email: string) => void;
  signOut: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      hydrated: AUTH_MODE !== "supabase",
      signIn: (token, email) => set({ token, email, hydrated: true }),
      signOut: () => {
        set({ token: null, email: null });
        if (AUTH_MODE === "supabase") void supabase.auth.signOut();
      },
    }),
    { name: "gp-auth", partialize: (state) => ({ token: state.token, email: state.email }) },
  ),
);

// Supabase owns the real session (silent refresh, multi-tab sign-out); this store just mirrors
// it so api.ts and every page can keep reading useAuth.getState().token unchanged (INF-06).
// onAuthStateChange fires once immediately with the restored session (or null), which is what
// resolves `hydrated`.
if (AUTH_MODE === "supabase") {
  supabase.auth.onAuthStateChange((_event, session) => {
    useAuth.setState({ token: session?.access_token ?? null, email: session?.user.email ?? null, hydrated: true });
  });
}
