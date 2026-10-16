import { describe, expect, it } from "vitest";

import viteConfig from "../../vite.config";

type ProxyRule = {
  target?: string;
  rewrite?: (path: string) => string;
};

function resolveBackendPath(path: string): string {
  const proxy = viteConfig.server?.proxy;

  if (!proxy) {
    throw new Error("Vite proxy configuration is missing");
  }

  for (const [prefix, rule] of Object.entries(proxy)) {
    if (!path.startsWith(prefix)) {
      continue;
    }

    if (typeof rule === "string") {
      return path;
    }

    const typedRule = rule as ProxyRule;

    if (!typedRule.target) {
      throw new Error("Proxy target is missing");
    }

    return typedRule.rewrite?.(path) ?? path;
  }

  throw new Error(`No proxy matches ${path}`);
}

describe("V1/V2 API proxy routing", () => {
  it("preserves the existing V1 route", () => {
    expect(resolveBackendPath("/api/trip-evaluations")).toBe(
      "/trip-evaluations",
    );
  });

  it.each([
    "/api/v2/me",
    "/api/v2/preferences",
    "/api/v2/vehicles",
    "/api/v2/trip-evaluations",
  ])("preserves authenticated V2 path %s", (path) => {
    expect(resolveBackendPath(path)).toBe(path);
  });

  it("preserves V2 nested resource paths", () => {
    expect(
      resolveBackendPath(
        "/api/v2/vehicles/123e4567-e89b-12d3-a456-426614174000",
      ),
    ).toBe("/api/v2/vehicles/123e4567-e89b-12d3-a456-426614174000");
  });
});
