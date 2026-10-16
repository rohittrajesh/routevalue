import { getNeonAuthClient } from "./neonClient";

export type AuthSessionStatus =
  "loading" | "authenticated" | "unauthenticated" | "error";

export interface AuthSessionState {
  status: AuthSessionStatus;
  userId: string | null;
  userEmail: string | null;
}

interface SessionUser {
  id: string;
  email: string;
}

function isSessionUser(value: unknown): value is SessionUser {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  if (!("id" in value) || !("email" in value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    value.id.trim().length > 0 &&
    typeof value.email === "string" &&
    value.email.trim().length > 0
  );
}

export function getSessionUser(data: unknown): SessionUser | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }

  if (!("user" in data)) {
    return null;
  }

  return isSessionUser(data.user) ? data.user : null;
}

export function resolveAuthSessionState(
  isPending: boolean,
  user: SessionUser | null | undefined,
  hasError: boolean,
): AuthSessionState {
  if (isPending) {
    return {
      status: "loading",
      userId: null,
      userEmail: null,
    };
  }

  if (hasError) {
    return {
      status: "error",
      userId: null,
      userEmail: null,
    };
  }

  if (!user) {
    return {
      status: "unauthenticated",
      userId: null,
      userEmail: null,
    };
  }

  return {
    status: "authenticated",
    userId: user.id,
    userEmail: user.email,
  };
}

export function useAuthSession(): AuthSessionState {
  const authClient = getNeonAuthClient();

  const session = authClient.adapter.useSession();

  const sessionData: unknown = session.data;

  return resolveAuthSessionState(
    session.isPending,
    getSessionUser(sessionData),
    session.error !== null && session.error !== undefined,
  );
}
