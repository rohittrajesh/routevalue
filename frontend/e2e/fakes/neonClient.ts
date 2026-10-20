// Resolved only by vite.e2e.config.ts. Production always uses real Neon Auth.
function identity(): string | null {
  return window.localStorage.getItem("browser-test-user");
}

export function getNeonAuthClient() {
  return {
    getJWTToken: async () => (identity() ? `browser-test:${identity()}` : null),
    adapter: {
      useSession: () => ({
        isPending: false,
        error: null,
        data: identity()
          ? { user: { id: identity(), email: "browser@example.test" } }
          : null,
      }),
      signOut: async () => {
        window.localStorage.removeItem("browser-test-user");
        window.location.reload();
        return { data: {}, error: null };
      },
      signIn: {
        email: async () => ({
          error: "Test session must be seeded by Playwright",
        }),
      },
      signUp: {
        email: async () => ({
          error: "Test session must be seeded by Playwright",
        }),
      },
    },
  };
}
