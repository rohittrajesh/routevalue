import { useState, type FormEvent } from "react";

import { getNeonAuthClient } from "./neonClient";

type AuthMode = "sign-in" | "sign-up";

function isSuccessfulAuthResult(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  if ("error" in value && value.error != null) {
    return false;
  }

  return "data" in value && value.data != null;
}

export default function AuthPanel() {
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function changeMode() {
    if (isSubmitting) {
      return;
    }

    setMode((current) => (current === "sign-in" ? "sign-up" : "sign-in"));
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

    try {
      const auth = getNeonAuthClient();

      const result: unknown =
        mode === "sign-in"
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
        throw new Error("Authentication was not accepted");
      }

      setPassword("");
      setNotice("Request completed. Waiting for session confirmation...");
    } catch {
      setError(
        mode === "sign-in"
          ? "Sign-in failed. Check your credentials and try again."
          : "Account creation failed. Check your information and try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="v2-auth-card" aria-labelledby="v2-auth-title">
      <p className="eyebrow">RouteValue account</p>

      <h2 id="v2-auth-title">
        {mode === "sign-in" ? "Sign in" : "Create your account"}
      </h2>

      <p className="muted">
        {mode === "sign-in"
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

        {error && (
          <p className="v2-feedback v2-error" role="alert">
            {error}
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
            : mode === "sign-in"
              ? "Sign in"
              : "Create account"}
        </button>
      </form>

      <p className="v2-auth-switch">
        {mode === "sign-in" ? "New to RouteValue?" : "Already have an account?"}{" "}
        <button type="button" onClick={changeMode}>
          {mode === "sign-in" ? "Create an account" : "I have an account"}
        </button>
      </p>
    </section>
  );
}
