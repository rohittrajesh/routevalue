import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",

  testMatch: "**/*.spec.ts",

  fullyParallel: true,

  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },

  webServer: [
    {
      command:
        "cd ../backend && uv run uvicorn browser_server:create_browser_app --factory --app-dir tests --host 127.0.0.1 --port 4174",
      url: "http://127.0.0.1:4174/health",
      reuseExistingServer: false,
      env: { ROUTEVALUE_BROWSER_TEST_SERVER: "1", PYTHONPATH: "src" },
    },
    {
      command: "npm run dev:e2e",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
    },
  ],

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
    {
      name: "mobile-chromium",
      testMatch: "**/v2-workflow.spec.ts",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
