import { useState, type FormEvent } from "react";

import { isSuccessfulAuthResult } from "./authResult";
import { getNeonAuthClient } from "./neonClient";
import { authErrorMessage, recoveryErrorMessage } from "./authErrors";

const emailNotice =
  "If this account is eligible, check your inbox for the authentication message. You can then return to sign in.";

type AuthMode = "sign-in" | "sign-up" | "recover" | "verify";

export default function AuthPanel({ onSignedIn }: { onSignedIn?: () => void }) {
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const localhostUrl =
    import.meta.env.DEV && window.location.hostname === "127.0.0.1"
      ? `${window.location.protocol}//localhost:${window.location.port}/v2`
      : null;

  function changeMode(next: AuthMode) {
    if (isSubmitting) {
      return;
    }

    setMode(next);
    setPassword("");
    setError(null);
    setNotice(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setNotice(null);

    const normalizedEmail = email.trim();
    const emailOnly = mode === "recover" || mode === "verify";

    try {
      const auth = getNeonAuthClient();

      const result: unknown =
        mode === "recover"
          ? await auth.adapter.requestPasswordReset({
              email: normalizedEmail,
              redirectTo: `${window.location.origin}/v2/reset-password`,
            })
          : mode === "verify"
            ? await auth.adapter.sendVerificationEmail({
                email: normalizedEmail,
                callbackURL: `${window.location.origin}/v2`,
              })
            : mode === "sign-in"
              ? await auth.adapter.signIn.email({
                  email: normalizedEmail,
                  password,
                })
              : await auth.adapter.signUp.email({
                  name: name.trim(),
                  email: normalizedEmail,
                  password,
                });

      if (!isSuccessfulAuthResult(result)) {
        throw typeof result === "object" && result !== null && "error" in result
          ? result.error
          : new Error("Authentication was not accepted");
      }

      setPassword("");
      if (mode === "sign-in") onSignedIn?.();
      setNotice(
        emailOnly
          ? emailNotice
          : mode === "sign-in"
            ? "Request completed. Waiting for session confirmation..."
            : "Account request completed. Check your inbox if email verification is required, then sign in.",
      );
    } catch (failure: unknown) {
      const code =
        typeof failure === "object" &&
        failure !== null &&
        "code" in failure &&
        typeof failure.code === "string"
          ? failure.code.toLowerCase()
          : "";
      if (
        emailOnly &&
        ["user_not_found", "email_already_verified"].includes(code)
      ) {
        setNotice(emailNotice);
        return;
      }
      setError(
        emailOnly
          ? recoveryErrorMessage(failure)
          : authErrorMessage(failure, mode === "sign-up"),
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="v2-auth-card" aria-labelledby="v2-auth-title">
      <p className="eyebrow">RouteValue account</p>

      <h2 id="v2-auth-title">
        {mode === "recover"
          ? "Reset your password"
          : mode === "verify"
            ? "Verify your email"
            : mode === "sign-in"
              ? "Sign in"
              : "Create your account"}
      </h2>

      <p className="muted">
        {mode === "recover" || mode === "verify"
          ? "Enter your account email to request a new message from the authentication service."
          : mode === "sign-in"
            ? "Access your saved vehicles and personalized driving preferences."
            : "Create an account to save vehicles and personalize your routes."}
      </p>

      <form className="v2-auth-form" onSubmit={handleSubmit}>
        {mode === "sign-up" && (
          <label className="field">
            <span>Name</span>
            <input
              type="text"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
              disabled={isSubmitting}
            />
          </label>
        )}

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            disabled={isSubmitting}
          />
        </label>

        {(mode === "sign-in" || mode === "sign-up") && (
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={
                mode === "sign-in" ? "current-password" : "new-password"
              }
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              required
              disabled={isSubmitting}
            />
          </label>
        )}

        {error && (
          <p className="v2-feedback v2-error" role="alert">
            {error}
            {localhostUrl && error.includes("app address") && (
              <>
                {" "}
                <a href={localhostUrl}>Open RouteValue on localhost</a>
              </>
            )}
          </p>
        )}

        {notice && (
          <p className="v2-feedback" role="status">
            {notice}
          </p>
        )}

        <button
          type="submit"
          className="v2-primary-button"
          disabled={isSubmitting}
        >
          {isSubmitting
            ? "Please wait..."
            : mode === "recover"
              ? "Send reset email"
              : mode === "verify"
                ? "Send verification email"
                : mode === "sign-in"
                  ? "Sign in"
                  : "Create account"}
        </button>
      </form>

      <p className="v2-auth-switch">
        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => changeMode(mode === "sign-in" ? "sign-up" : "sign-in")}
        >
          {mode === "sign-in" ? "Create an account" : "I have an account"}
        </button>
      </p>
      {mode === "sign-in" && (
        <p className="v2-auth-switch">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => changeMode("recover")}
          >
            Forgot password?
          </button>{" "}
          <button
            type="button"
            disabled={isSubmitting}
            onClick={() => changeMode("verify")}
          >
            Resend verification email
          </button>
        </p>
      )}
    </section>
  );
}
