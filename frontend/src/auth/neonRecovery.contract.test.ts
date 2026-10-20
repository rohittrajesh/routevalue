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

it("maps the real SDK OTP request, verification and reset methods to distinct endpoints", async () => {
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify({ success: true }), {
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const auth = createInternalNeonAuth("https://auth.example.test/neondb/auth", {
    adapter: BetterAuthReactAdapter(),
    allowAnonymous: false,
  });
  await auth.adapter.emailOtp.sendVerificationOtp({
    email: "someone@example.test",
    type: "email-verification",
  });
  await auth.adapter.emailOtp.verifyEmail({
    email: "someone@example.test",
    otp: "000000",
  });
  await auth.adapter.emailOtp.requestPasswordReset({
    email: "someone@example.test",
  });
  await auth.adapter.emailOtp.resetPassword({
    email: "someone@example.test",
    otp: "000000",
    password: "synthetic-password",
  });
  expect(
    fetchMock.mock.calls.map(([url, init]: [string, RequestInit]) => ({
      path: new URL(String(url)).pathname,
      method: init.method,
      body: JSON.parse(String(init.body)) as unknown,
    })),
  ).toEqual([
    {
      path: "/neondb/auth/email-otp/send-verification-otp",
      method: "POST",
      body: { email: "someone@example.test", type: "email-verification" },
    },
    {
      path: "/neondb/auth/email-otp/verify-email",
      method: "POST",
      body: { email: "someone@example.test", otp: "000000" },
    },
    {
      path: "/neondb/auth/email-otp/request-password-reset",
      method: "POST",
      body: { email: "someone@example.test" },
    },
    {
      path: "/neondb/auth/email-otp/reset-password",
      method: "POST",
      body: {
        email: "someone@example.test",
        otp: "000000",
        password: "synthetic-password",
      },
    },
  ]);
});

it("exposes an unmapped OTP rejection as the SDK's normalized validation error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ code: "INVALID_OTP", message: "Invalid OTP" }),
          {
            status: 400,
            statusText: "Bad Request",
            headers: { "Content-Type": "application/json" },
          },
        ),
    ),
  );
  const auth = createInternalNeonAuth("https://auth.example.test/neondb/auth", {
    adapter: BetterAuthReactAdapter(),
    allowAnonymous: false,
  });
  let failure: unknown;
  try {
    const result = await auth.adapter.emailOtp.verifyEmail({
      email: "someone@example.test",
      otp: "000000",
    });
    failure = result.error;
  } catch (error: unknown) {
    failure = error;
  }
  expect(failure).toMatchObject({ code: "validation_failed", status: 400 });
});
