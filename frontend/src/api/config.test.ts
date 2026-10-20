import { afterEach, describe, expect, it, vi } from "vitest";

import { getApiBaseUrl, getV2ApiBaseUrl } from "./config";

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

// A production base must not accidentally turn /api/v2/me into /v2/me.
describe("getV2ApiBaseUrl", () => {
  it("uses the local V2 proxy by default", () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.stubEnv("VITE_V2_API_BASE_URL", "");
    expect(getV2ApiBaseUrl()).toBe("/api/v2");
  });
  it("retains /api/v2 with the existing production V1 origin", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://routevalue-api.onrender.com");
    vi.stubEnv("VITE_V2_API_BASE_URL", "");
    expect(getV2ApiBaseUrl()).toBe(
      "https://routevalue-api.onrender.com/api/v2",
    );
    expect(getApiBaseUrl()).toBe("https://routevalue-api.onrender.com");
  });
  it("allows an explicit separate V2 backend", () => {
    vi.stubEnv("VITE_V2_API_BASE_URL", "https://api.example.test/api/v2/");
    expect(getV2ApiBaseUrl()).toBe("https://api.example.test/api/v2");
  });
  it.each([
    "/\\attacker.test/api/v2",
    "http://api.example.test/api/v2",
    "https://user:secret@api.example.test/api/v2",
    "//api.example.test/api/v2",
    "https://api.example.test/api/v2?token=secret",
    "/api/v2#token",
  ])("rejects unsafe V2 base %s", (url) => {
    vi.stubEnv("VITE_V2_API_BASE_URL", url);
    expect(() => getV2ApiBaseUrl()).toThrow("VITE_V2_API_BASE_URL");
  });
});

it("rejects insecure V2 fallback origins even when legacy V1 configuration allows them", () => {
  vi.stubEnv("VITE_API_BASE_URL", "http://api.example.test");
  vi.stubEnv("VITE_V2_API_BASE_URL", "");
  expect(() => getV2ApiBaseUrl()).toThrow("VITE_V2_API_BASE_URL");
});
