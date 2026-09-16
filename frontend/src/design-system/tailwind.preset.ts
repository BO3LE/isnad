import type { Config } from "tailwindcss";

// DESIGN-SYSTEM.md §24.3 — every value points at a CSS custom property from tokens.css.
const v = (name: string) => `var(--${name})`;
const tones = ["pending", "running", "retrying", "approval", "success", "failed", "skipped", "cancelled"] as const;

export default {
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: v("color-bg"), sunken: v("color-bg-sunken") },
        surface: {
          DEFAULT: v("color-surface"),
          raised: v("color-surface-raised"),
          hover: v("color-surface-hover"),
          inverse: v("color-surface-inverse"),
        },
        border: { DEFAULT: v("color-border"), strong: v("color-border-strong"), hover: v("color-border-hover") },
        text: { DEFAULT: v("color-text"), muted: v("color-text-muted"), subtle: v("color-text-subtle"), inverse: v("color-text-inverse") },
        accent: { DEFAULT: v("color-accent"), on: v("color-on-accent"), text: v("color-accent-text") },
        interactive: { DEFAULT: v("color-interactive"), hover: v("color-interactive-hover") },
        focus: v("color-focus"),
        selection: v("color-selection-bg"),
        danger: { DEFAULT: v("color-danger"), on: v("color-on-danger") },
        status: Object.fromEntries(
          tones.map((t) => [t, { solid: v(`status-${t}-solid`), fg: v(`status-${t}-fg`), bg: v(`status-${t}-bg`) }]),
        ),
      },
      fontFamily: {
        sans: [v("font-sans")],
        serif: [v("font-serif")],
        mono: [v("font-mono")],
      },
      fontSize: {
        "display-lg": ["56px", { lineHeight: "62px", letterSpacing: "-0.02em", fontWeight: "500" }],
        "display-md": ["44px", { lineHeight: "48px", letterSpacing: "-0.02em", fontWeight: "500" }],
        "heading-xl": ["32px", { lineHeight: "38px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "heading-lg": ["24px", { lineHeight: "30px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "heading-md": ["18px", { lineHeight: "24px", letterSpacing: "-0.005em", fontWeight: "600" }],
        "heading-sm": ["15px", { lineHeight: "22px", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px" }],
        "body-md": ["14px", { lineHeight: "21px" }],
        "body-md-strong": ["14px", { lineHeight: "21px", fontWeight: "500" }],
        "body-sm": ["13px", { lineHeight: "18px", letterSpacing: "0.005em" }],
        caption: ["12px", { lineHeight: "16px", letterSpacing: "0.005em", fontWeight: "500" }],
        overline: ["11px", { lineHeight: "16px", letterSpacing: "0.06em", fontWeight: "600" }],
        "mono-md": ["13px", { lineHeight: "20px" }],
        "mono-sm": ["12px", { lineHeight: "16px" }],
      },
      // DESIGN-SYSTEM.md §10 — the whole scale, so nothing has to guess a raw number.
      zIndex: {
        canvas: "0",
        "canvas-controls": "5",
        shell: "10",
        drawer: "20",
        dropdown: "30",
        sheet: "40",
        dialog: "50",
        toast: "60",
        tooltip: "70",
      },
      borderRadius: { xs: v("radius-xs"), sm: v("radius-sm"), md: v("radius-md"), lg: v("radius-lg"), xl: v("radius-xl") },
      boxShadow: { 1: v("shadow-1"), 2: v("shadow-2"), 3: v("shadow-3"), 4: v("shadow-4") },
      transitionTimingFunction: { standard: v("ease-standard"), enter: v("ease-enter"), exit: v("ease-exit") },
      keyframes: {
        "pulse-ring": { "0%": { transform: "scale(1)", opacity: "0.5" }, "100%": { transform: "scale(1.6)", opacity: "0" } },
        "progress-slide": { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(300%)" } },
      },
      animation: {
        "pulse-ring": "pulse-ring 1600ms cubic-bezier(0, 0, 0.2, 1) infinite",
        "progress-slide": "progress-slide 1200ms linear infinite",
      },
    },
  },
} satisfies Partial<Config>;
