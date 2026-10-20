import { defineConfig, devices } from "@playwright/test";

// Real production bundling and real Neon SDK. Network responses are synthetic.
// This must never inherit local credentials or contact paid/live providers.
export default defineConfig({
  testDir: "./release-e2e",
  use: { baseURL: "http://127.0.0.1:4176", trace: "on-first-retry" },
  webServer: {
    command:
      "npm run build -- --outDir dist-release-smoke && npm run preview -- --host 127.0.0.1 --port 4176 --strictPort --outDir dist-release-smoke",
    url: "http://127.0.0.1:4176",
    reuseExistingServer: false,
    env: {
      VITE_V2_HOMEPAGE: "1",
      VITE_API_BASE_URL: "https://api.example.invalid",
      VITE_V2_API_BASE_URL: "https://api.example.invalid/api/v2",
      VITE_AUTH_URL: "https://auth.example.invalid/neondb/auth",
      VITE_GOOGLE_MAPS_API_KEY: "",
    },
  },
  projects: [
    { name: "release-desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "release-mobile", use: { ...devices["Pixel 7"] } },
  ],
});
