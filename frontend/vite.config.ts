/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    // Polling makes hot reload work through Docker bind mounts on macOS and Windows.
    watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === "true" },
  },
  test: {
    // Pinned, not inherited: on a UTC machine a local-vs-UTC assertion is a tautology, so any test
    // of the log's time zone toggle would pass without the code honouring the zone at all.
    env: { TZ: "Asia/Riyadh" },
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
