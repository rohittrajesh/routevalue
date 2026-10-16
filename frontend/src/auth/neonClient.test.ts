import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createAuthMock, adapterMock } = vi.hoisted(() => ({
  createAuthMock: vi.fn(),
  adapterMock: vi.fn(),
}));

vi.mock("@neondatabase/auth", () => ({
  createInternalNeonAuth: createAuthMock,
}));

vi.mock("@neondatabase/auth/react/adapters", () => ({
  BetterAuthReactAdapter: adapterMock,
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.unstubAllEnvs();

  adapterMock.mockReturnValue({
    name: "test-react-adapter-builder",
  });

  createAuthMock.mockReturnValue({
    adapter: {
      name: "test-react-client",
    },
    getJWTToken: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Neon Auth client", () => {
  it("requires an Auth URL", async () => {
    vi.stubEnv("VITE_AUTH_URL", "");

    const { getNeonAuthClient } = await import("./neonClient");

    expect(() => getNeonAuthClient()).toThrow(
      "VITE_AUTH_URL must be configured",
    );

    expect(createAuthMock).not.toHaveBeenCalled();
  });

  it("rejects invalid HTTPS configuration", async () => {
    vi.stubEnv("VITE_AUTH_URL", "http://example.com/auth");

    const { getNeonAuthClient } = await import("./neonClient");

    expect(() => getNeonAuthClient()).toThrow(
      "VITE_AUTH_URL must be a valid HTTPS URL",
    );
  });

  it("rejects embedded credentials", async () => {
    vi.stubEnv("VITE_AUTH_URL", "https://user:password@example.com/auth");

    const { getNeonAuthClient } = await import("./neonClient");

    expect(() => getNeonAuthClient()).toThrow(
      "VITE_AUTH_URL must be a valid HTTPS URL",
    );
  });

  it("initializes the React adapter and JWT client", async () => {
    vi.stubEnv("VITE_AUTH_URL", "https://auth.example.com/auth/");

    const { getNeonAuthClient } = await import("./neonClient");

    const client = getNeonAuthClient();

    expect(client.adapter).toEqual({
      name: "test-react-client",
    });

    expect(typeof client.getJWTToken).toBe("function");

    expect(createAuthMock).toHaveBeenCalledWith(
      "https://auth.example.com/auth",
      {
        adapter: {
          name: "test-react-adapter-builder",
        },
        allowAnonymous: false,
      },
    );
  });

  it("reuses the same authentication instance", async () => {
    vi.stubEnv("VITE_AUTH_URL", "https://auth.example.com/auth");

    const { getNeonAuthClient } = await import("./neonClient");

    const first = getNeonAuthClient();
    const second = getNeonAuthClient();

    expect(first).toBe(second);
    expect(createAuthMock).toHaveBeenCalledTimes(1);
    expect(adapterMock).toHaveBeenCalledTimes(1);
  });
});
