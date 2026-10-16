import { describe, expect, it } from "vitest";

import { getSessionUser, resolveAuthSessionState } from "./useAuthSession";

describe("getSessionUser", () => {
  it("extracts a valid user", () => {
    expect(
      getSessionUser({
        user: {
          id: "user-123",
          email: "test@example.com",
          name: "Test User",
        },
      }),
    ).toEqual({
      id: "user-123",
      email: "test@example.com",
      name: "Test User",
    });
  });

  it("rejects invalid session payloads", () => {
    expect(getSessionUser(null)).toBeNull();
    expect(getSessionUser({})).toBeNull();
    expect(getSessionUser({ user: null })).toBeNull();
    expect(getSessionUser({ user: "invalid" })).toBeNull();
  });

  it("rejects incomplete user identities", () => {
    expect(
      getSessionUser({
        user: {
          id: "",
          email: "test@example.com",
        },
      }),
    ).toBeNull();

    expect(
      getSessionUser({
        user: {
          id: "user-123",
        },
      }),
    ).toBeNull();
  });
});

describe("resolveAuthSessionState", () => {
  it("reports loading while pending", () => {
    expect(resolveAuthSessionState(true, null, false)).toEqual({
      status: "loading",
      userId: null,
      userEmail: null,
    });
  });

  it("reports unauthenticated without a session", () => {
    expect(resolveAuthSessionState(false, null, false)).toEqual({
      status: "unauthenticated",
      userId: null,
      userEmail: null,
    });
  });

  it("reports an authenticated session", () => {
    expect(
      resolveAuthSessionState(
        false,
        {
          id: "user-123",
          email: "test@example.com",
        },
        false,
      ),
    ).toEqual({
      status: "authenticated",
      userId: "user-123",
      userEmail: "test@example.com",
    });
  });

  it("reports session errors separately", () => {
    expect(resolveAuthSessionState(false, null, true)).toEqual({
      status: "error",
      userId: null,
      userEmail: null,
    });
  });

  it("prioritizes loading while pending", () => {
    expect(resolveAuthSessionState(true, null, true).status).toBe("loading");
  });

  it("does not expose user information during errors", () => {
    expect(
      resolveAuthSessionState(
        false,
        {
          id: "user-123",
          email: "test@example.com",
        },
        true,
      ),
    ).toEqual({
      status: "error",
      userId: null,
      userEmail: null,
    });
  });
});
