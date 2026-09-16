import { create } from "zustand";
import { persist } from "zustand/middleware";

// DESIGN-SYSTEM.md §04: three choices, two painted themes. "system" is resolved here rather than
// in CSS so tokens.css needs only one dark rule — see the comment above :root[data-theme="dark"].
// Shipping dark is decision D-05; the tokens are ready either way.
export type ThemeChoice = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function prefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.(DARK_QUERY).matches === true;
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice !== "system") return choice;
  return prefersDark() ? "dark" : "light";
}

export function applyTheme(choice: ThemeChoice): void {
  document.documentElement.setAttribute("data-theme", resolveTheme(choice));
}

export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "gp-theme",
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);

interface ThemeState {
  theme: ThemeChoice;
  setTheme: (theme: ThemeChoice) => void;
}

// Follow the OS while the user is on "system" — otherwise their explicit choice wins.
if (typeof window !== "undefined" && window.matchMedia) {
  window.matchMedia(DARK_QUERY).addEventListener("change", () => {
    const { theme } = useTheme.getState();
    if (theme === "system") applyTheme(theme);
  });
}
