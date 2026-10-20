// Real installed SDK; only HTTP transport is intercepted. No provider emails sent.
import { afterEach, expect, it, vi } from "vitest";
import { createInternalNeonAuth } from "@neondatabase/auth";
import { BetterAuthReactAdapter } from "@neondatabase/auth/react/adapters";

afterEach(() => vi.unstubAllGlobals());

it("maps recovery and verification methods to the managed Neon endpoint contract", async () => {
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify({ status: true }), {
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const auth = createInternalNeonAuth("https://auth.example.test/neondb/auth", {
    adapter: BetterAuthReactAdapter(),
    allowAnonymous: false,
  });
  await auth.adapter.requestPasswordReset({
    email: "someone@example.test",
    redirectTo: "http://localhost:5173/v2/reset-password",
  });
  await auth.adapter.sendVerificationEmail({
    email: "someone@example.test",
    callbackURL: "http://localhost:5173/v2",
  });
  await auth.adapter.resetPassword({
    token: "synthetic-token",
    newPassword: "synthetic-password",
  });
  const requests = fetchMock.mock.calls.map(
    ([url, init]: [string, RequestInit]) => ({
      url: String(url),
      method: init.method,
      body: JSON.parse(String(init.body)) as unknown,
    }),
  );
  expect(requests).toEqual([
    {
      url: "https://auth.example.test/neondb/auth/request-password-reset",
      method: "POST",
      body: {
        email: "someone@example.test",
        redirectTo: "http://localhost:5173/v2/reset-password",
      },
    },
    {
      url: "https://auth.example.test/neondb/auth/send-verification-email",
      method: "POST",
      body: {
        email: "someone@example.test",
        callbackURL: "http://localhost:5173/v2",
      },
    },
    {
      url: "https://auth.example.test/neondb/auth/reset-password",
      method: "POST",
      body: { token: "synthetic-token", newPassword: "synthetic-password" },
    },
  ]);
});
