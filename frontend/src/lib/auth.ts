import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  email: string | null;
  signIn: (token: string, email: string) => void;
  signOut: () => void;
}

// TODO(W2, Ahmed + Hasan): swap dev-login for Supabase Auth (@supabase/supabase-js) once D-01 is signed off.
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      signIn: (token, email) => set({ token, email }),
      signOut: () => set({ token: null, email: null }),
    }),
    { name: "gp-auth" },
  ),
);
