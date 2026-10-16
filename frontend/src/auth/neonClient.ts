import { createInternalNeonAuth, type NeonAuth } from "@neondatabase/auth";

import {
  BetterAuthReactAdapter,
  type BetterAuthReactAdapterInstance,
} from "@neondatabase/auth/react/adapters";

type NeonReactAuth = NeonAuth<BetterAuthReactAdapterInstance>;

let authClient: NeonReactAuth | null = null;

export function getNeonAuthUrl(): string {
  const configuredUrl = import.meta.env.VITE_AUTH_URL?.trim();

  if (!configuredUrl) {
    throw new Error("VITE_AUTH_URL must be configured");
  }

  let parsedUrl: URL;

  try {
    parsedUrl = new URL(configuredUrl);
  } catch {
    throw new Error("VITE_AUTH_URL must be a valid HTTPS URL");
  }

  if (
    parsedUrl.protocol !== "https:" ||
    !parsedUrl.hostname ||
    parsedUrl.username ||
    parsedUrl.password ||
    parsedUrl.search ||
    parsedUrl.hash
  ) {
    throw new Error("VITE_AUTH_URL must be a valid HTTPS URL");
  }

  return parsedUrl.toString().replace(/\/+$/, "");
}

export function getNeonAuthClient(): NeonReactAuth {
  if (authClient === null) {
    authClient = createInternalNeonAuth<BetterAuthReactAdapterInstance>(
      getNeonAuthUrl(),
      {
        adapter: BetterAuthReactAdapter(),
        allowAnonymous: false,
      },
    );
  }

  return authClient;
}
