// Resolved only by vite.e2e.config.ts. Production always uses real Neon Auth.
import { useSyncExternalStore } from "react";

function identity(): string | null {
  return window.localStorage.getItem("browser-test-user");
}

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("browser-test-session", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("browser-test-session", listener);
  };
}

function notify() {
  window.dispatchEvent(new Event("browser-test-session"));
}

export function getNeonAuthClient() {
  return {
    getJWTToken: async () => (identity() ? `browser-test:${identity()}` : null),
    adapter: {
      useSession: () => {
        const userId = useSyncExternalStore(subscribe, identity);
        return {
          isPending: false,
          error: null,
          data: userId
            ? { user: { id: userId, email: "browser@example.test" } }
            : null,
        };
      },
      requestPasswordReset: async () => ({
        data: { status: true },
        error: null,
      }),
      sendVerificationEmail: async () => ({
        data: { status: true },
        error: null,
      }),
      resetPassword: async ({
        token,
      }: {
        token: string;
        newPassword: string;
      }) =>
        token === "browser-test-reset-token"
          ? { data: { status: true }, error: null }
          : { data: null, error: { code: "INVALID_TOKEN" } },
      signOut: async () => {
        window.localStorage.removeItem("browser-test-user");
        notify();
        return { data: { success: true }, error: null };
      },
      signIn: {
        email: async ({
          email,
          password,
        }: {
          email: string;
          password: string;
        }) => {
          const account = window.localStorage.getItem("browser-test-account");
          if (
            !account ||
            email !== "browser@example.test" ||
            password !== "synthetic-password"
          ) {
            return { data: null, error: { code: "invalid_credentials" } };
          }
          window.localStorage.setItem("browser-test-user", account);
          notify();
          return { data: { success: true }, error: null };
        },
      },
      signUp: {
        email: async () => ({ data: { user: {} }, error: null }),
      },
    },
  };
}
