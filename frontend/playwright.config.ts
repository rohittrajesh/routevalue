import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",

  testMatch: "**/*.spec.ts",

  fullyParallel: true,

  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },

  webServer: {
    command: "npm run dev:e2e",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
