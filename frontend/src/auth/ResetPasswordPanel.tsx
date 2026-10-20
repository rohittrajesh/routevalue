import { useLayoutEffect, useState, type FormEvent } from "react";

import "../V2App.css";
import "../WorkspaceTheme.css";

import { getNeonAuthClient } from "./neonClient";
import { isSuccessfulAuthResult } from "./authResult";
import { recoveryErrorMessage } from "./authErrors";
import { requireSignIn } from "./sessionBoundary";

function readToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  const tokens = params.getAll("token");
  const token = tokens[0];
  return !params.has("error") &&
    tokens.length === 1 &&
    token &&
    token.length <= 2048
    ? token
    : null;
}

export default function ResetPasswordPanel() {
  const [token, setToken] = useState(readToken);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [complete, setComplete] = useState(false);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useLayoutEffect(() => {
    // Keep the token in component memory only; never carry it into sign-in URLs.
    window.history.replaceState(null, "", "/v2/reset-password");
  }, []);

  async function finishSignOut() {
    setPending(true);
    setError(null);
    try {
      const result: unknown = await getNeonAuthClient().adapter.signOut({});
      if (!isSuccessfulAuthResult(result)) throw null;
      setSignedOut(true);
    } catch {
      setError(
        "Your password was updated, but sign-out could not be confirmed. Retry sign-out before returning.",
      );
    } finally {
      setPending(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !token) return;
    if (password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const result: unknown = await getNeonAuthClient().adapter.resetPassword({
        newPassword: password,
        token,
      });
      if (!isSuccessfulAuthResult(result)) {
        throw typeof result === "object" && result !== null && "error" in result
          ? result.error
          : null;
      }
      setPassword("");
      setConfirmation("");
      requireSignIn("expired");
      setToken(null);
      setComplete(true);
      await finishSignOut();
    } catch (failure: unknown) {
      setError(recoveryErrorMessage(failure));
    } finally {
      setPassword("");
      setConfirmation("");
      setPending(false);
    }
  }

  return (
    <main className="v2-app rv-reset">
      <section className="v2-auth-card" aria-labelledby="reset-title">
        <p className="eyebrow">RouteValue account</p>
        <h1 id="reset-title">Reset your password</h1>
        {complete ? (
          <div>
            <p role="status">
              Your password was updated.
              {signedOut && " Return to sign in with your new password."}
            </p>
            {!signedOut && (
              <button
                type="button"
                disabled={pending}
                onClick={() => {
                  void finishSignOut();
                }}
              >
                Retry sign-out
              </button>
            )}
            {error && <p role="alert">{error}</p>}
          </div>
        ) : !token ? (
          <p role="alert">
            This reset link is missing or invalid. Request a new email from sign
            in.
          </p>
        ) : (
          <form className="v2-auth-form" onSubmit={submit}>
            <label className="field">
              <span>New password</span>
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                disabled={pending}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Confirm new password</span>
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                disabled={pending}
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </label>
            {error && <p role="alert">{error}</p>}
            <button
              className="v2-primary-button"
              type="submit"
              disabled={pending}
            >
              {pending ? "Please wait..." : "Update password"}
            </button>
          </form>
        )}
        {(!complete || signedOut) && (
          <p>
            <a href="/v2">Return to sign in</a>
          </p>
        )}
      </section>
    </main>
  );
}
