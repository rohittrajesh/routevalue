import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getApiBaseUrl", () => {
  it("uses the local API proxy when no production base URL is configured", () => {
    vi.stubEnv("VITE_API_BASE_URL", "");

    expect(getApiBaseUrl()).toBe("/api");
  });

  it("uses the configured production API base URL", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://routevalue-backend.example.com");

    expect(getApiBaseUrl()).toBe("https://routevalue-backend.example.com");
  });

  it("removes trailing slashes from the configured base URL", () => {
    vi.stubEnv(
      "VITE_API_BASE_URL",
      "https://routevalue-backend.example.com///",
    );

    expect(getApiBaseUrl()).toBe("https://routevalue-backend.example.com");
  });
});
