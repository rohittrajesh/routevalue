import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthSession } from "./useAuthSession";

const { useSessionMock } = vi.hoisted(() => ({
  useSessionMock: vi.fn(),
}));

vi.mock("./neonClient", () => ({
  getNeonAuthClient: () => ({
    adapter: {
      useSession: useSessionMock,
    },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useAuthSession integration", () => {
  it("recognizes an authenticated user", () => {
    useSessionMock.mockReturnValue({
      data: {
        user: {
          id: "user-123",
          email: "test@example.com",
          name: "Test User",
        },
        session: {
          id: "session-123",
        },
      },
      isPending: false,
      error: null,
    });

    const { result } = renderHook(() => useAuthSession());

    expect(result.current).toEqual({
      status: "authenticated",
      userId: "user-123",
      userEmail: "test@example.com",
    });
  });

  it("recognizes a signed-out user", () => {
    useSessionMock.mockReturnValue({
      data: null,
      isPending: false,
      error: null,
    });

    const { result } = renderHook(() => useAuthSession());

    expect(result.current.status).toBe("unauthenticated");
  });

  it("preserves loading state", () => {
    useSessionMock.mockReturnValue({
      data: null,
      isPending: true,
      error: null,
    });

    const { result } = renderHook(() => useAuthSession());

    expect(result.current.status).toBe("loading");
  });

  it("distinguishes session errors from sign-out", () => {
    useSessionMock.mockReturnValue({
      data: null,
      isPending: false,
      error: new Error("Authentication unavailable"),
    });

    const { result } = renderHook(() => useAuthSession());

    expect(result.current.status).toBe("error");
  });

  it("rejects malformed session user data", () => {
    useSessionMock.mockReturnValue({
      data: {
        user: {
          id: "",
          email: "test@example.com",
        },
      },
      isPending: false,
      error: null,
    });

    const { result } = renderHook(() => useAuthSession());

    expect(result.current.status).toBe("unauthenticated");
  });
});
