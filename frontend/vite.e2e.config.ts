import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Keep the test aliases/optimizer separate from a concurrently running real
  // development app, and never inherit real API endpoints or browser keys.
  cacheDir: "node_modules/.vite-e2e",
  define: {
    "import.meta.env.VITE_API_BASE_URL": JSON.stringify("/api"),
    "import.meta.env.VITE_GOOGLE_MAPS_API_KEY": JSON.stringify(
      "browser-test-placeholder",
    ),
    "import.meta.env.VITE_AUTH_URL": JSON.stringify(
      "https://auth.example.invalid",
    ),
  },

  resolve: {
    alias: [
      {
        find: /^(?:\.\.?\/auth\/neonClient|\.\/neonClient)$/,
        replacement: fileURLToPath(
          new URL("./e2e/fakes/neonClient.ts", import.meta.url),
        ),
      },
      {
        find: "../integrations/googlePlaces",
        replacement: fileURLToPath(
          new URL("./e2e/fakes/googlePlaces.ts", import.meta.url),
        ),
      },
      {
        find: "../integrations/googleMaps",
        replacement: fileURLToPath(
          new URL("./e2e/fakes/googleMaps.ts", import.meta.url),
        ),
      },
    ],
  },
  server: {
    proxy: {
      "/api/v2": { target: "http://127.0.0.1:4174", changeOrigin: true },
    },
  },
});
