import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    // The router plugin must run before React's when code splitting is on.
    TanStackRouterVite({
      routeFileIgnorePattern: ".(test|spec).(tsx?|js)",
      // Route components load lazily, so SurveyJS stays out of the entry chunk.
      // Off under Vitest: route tests read `Route.options.component` directly.
      autoCodeSplitting: !process.env.VITEST,
    }),
    react(),
    tailwindcss(),
  ],
  // Read .env from the repo root, shared with the backend.
  envDir: resolve(import.meta.dirname, ".."),
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5174,
  },
  test: {
    environment: "happy-dom",
    // The happy-dom page origin differs from VITE_API_BASE_URL, so without this
    // every API call starts with a CORS preflight that no MSW handler answers.
    environmentOptions: {
      happyDOM: { settings: { fetch: { disableSameOriginPolicy: true } } },
    },
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // Playwright specs in e2e/ run with `npx playwright test`, not Vitest.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
