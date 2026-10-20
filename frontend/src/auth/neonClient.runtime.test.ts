import { afterEach, describe, expect, it, vi } from "vitest";
import { createInternalNeonAuth } from "@neondatabase/auth";
import { BetterAuthReactAdapter } from "@neondatabase/auth/react/adapters";
import { authErrorMessage } from "./authErrors";

afterEach(() => vi.unstubAllGlobals());

describe("real Neon SDK error integration", () => {
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
