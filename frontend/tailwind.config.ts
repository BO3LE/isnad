import type { Config } from "tailwindcss";
import designSystem from "./src/design-system/tailwind.preset";

export default {
  presets: [designSystem],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // Status classes are built from data at runtime (statusMeta.ts), so Tailwind can't see them in source.
  safelist: [{ pattern: /^(bg|text|border)-status-(pending|running|retrying|approval|success|failed|skipped|cancelled)-(solid|fg|bg)$/ }],
} satisfies Config;
