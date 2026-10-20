import { ApiRequestError } from "../api/tripEvaluations";

type SessionBoundaryReason = "expired" | "signed-out" | null;

interface SessionBoundary {
  version: number;
  reason: SessionBoundaryReason;
}

let boundary: SessionBoundary = { version: 0, reason: null };
let principal: string | null = null;
const listeners = new Set<() => void>();

export function getSessionBoundary(): SessionBoundary {
  return boundary;
}

export function subscribeToSessionBoundary(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function advance(reason: SessionBoundaryReason) {
  boundary = { version: boundary.version + 1, reason };
  listeners.forEach((listener) => listener());
}

export function isCurrentSessionPrincipal(userId: string | null): boolean {
  return principal === userId;
}

export function setSessionPrincipal(userId: string | null): void {
  if (principal !== userId) {
    principal = userId;
    advance(userId === null ? boundary.reason : null);
  }
}

export function requireSignIn(
  reason: Exclude<SessionBoundaryReason, null>,
): void {
  advance(reason);
}

export function confirmSignIn(): void {
  // The SDK may already have published the new principal before resolving sign-in.
  // Do not invalidate the profile requests started for that confirmed session.
  if (boundary.reason !== null) advance(null);
}

export function assertCurrentSession(started: SessionBoundary): void {
  if (started !== boundary) {
    throw new ApiRequestError(
      "Your session changed. Please try again after signing in.",
      401,
      "session_changed",
    );
  }
}
