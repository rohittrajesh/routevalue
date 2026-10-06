import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: [
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
});
