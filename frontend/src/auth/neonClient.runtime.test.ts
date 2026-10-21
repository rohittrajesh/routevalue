import { afterEach, describe, expect, it, vi } from "vitest";
import { createInternalNeonAuth } from "@neondatabase/auth";
import { BetterAuthReactAdapter } from "@neondatabase/auth/react/adapters";
import { authErrorMessage } from "./authErrors";

const originalResponseJson = Object.getOwnPropertyDescriptor(Response, "json")!;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  Object.defineProperty(Response, "json", originalResponseJson);
});

describe("real Neon SDK error integration", () => {
  it("reuses an authenticated session when the browser lacks static Response.json", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_AUTH_URL", "https://auth.example.test/auth");
    Object.defineProperty(Response, "json", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    const token = `fixture.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 900 }))}.signature`;
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            session: {
              id: "fixture-session",
              token: "opaque-session",
              userId: "fixture-user",
              expiresAt: new Date(Date.now() + 86400000).toISOString(),
            },
            user: {
              id: "fixture-user",
              name: "Fixture",
              email: "fixture@example.test",
              emailVerified: true,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
          }),
          {
            headers: {
              "content-type": "application/json",
              "set-auth-jwt": token,
            },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getNeonAuthClient } = await import("./neonClient");
    const auth = getNeonAuthClient();
    await expect(auth.getJWTToken()).resolves.toBe(token);
    await expect(auth.getJWTToken()).resolves.toBe(token);
    await expect(
      Promise.all([auth.getJWTToken(), auth.getJWTToken()]),
    ).resolves.toEqual([token, token]);
    expect(fetchMock).toHaveBeenCalledOnce();
  });
  it("preserves the actionable invalid-origin diagnosis after SDK normalization", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: "INVALID_ORIGIN", message: "Invalid origin" }),
          { status: 403, headers: { "content-type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const auth = createInternalNeonAuth("https://auth.example.test/auth", {
      adapter: BetterAuthReactAdapter(),
      allowAnonymous: false,
    });
    let failure: unknown;
    try {
      await auth.adapter.signIn.email({
        email: "fixture@example.test",
        password: "synthetic-test-value",
      });
    } catch (error: unknown) {
      failure = error;
    }
    expect(failure).toBeDefined();
    expect(authErrorMessage(failure, false)).toContain("use localhost");
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
