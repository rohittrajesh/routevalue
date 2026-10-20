import { useRef, useState, type FormEvent } from "react";

import { getNeonAuthClient } from "./neonClient";
import { isSuccessfulAuthResult } from "./authResult";
import { recoveryErrorMessage } from "./authErrors";
import { requireSignIn } from "./sessionBoundary";

const requestNotice =
  "If this account is eligible, check your inbox. Enter the email code below. Codes expire as described in the email.";

function failureCode(failure: unknown): string {
  return typeof failure === "object" &&
    failure !== null &&
    "code" in failure &&
    typeof failure.code === "string"
    ? failure.code.toLowerCase()
    : "";
}

function requireSuccess(result: unknown): void {
  if (!isSuccessfulAuthResult(result)) {
    throw typeof result === "object" && result !== null && "error" in result
      ? result.error
      : null;
  }
}

export default function EmailCodePanel({
  purpose,
  initialEmail,
  onBack,
}: {
  purpose: "verify" | "recover";
  initialEmail: string;
  onBack: (email: string) => void;
}) {
  const emailInput = useRef<HTMLInputElement>(null);
  const recovering = purpose === "recover";
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [enterCode, setEnterCode] = useState(!recovering);
  const [pending, setPending] = useState(false);
  const [complete, setComplete] = useState(false);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function requestCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    setNotice(null);
    setCode("");
    setPassword("");
    setConfirmation("");
    try {
      const otp = getNeonAuthClient().adapter.emailOtp;
      requireSuccess(
        recovering
          ? await otp.requestPasswordReset({ email: email.trim() })
          : await otp.sendVerificationOtp({
              email: email.trim(),
              type: "email-verification",
            }),
      );
      setEnterCode(true);
      setNotice(requestNotice);
    } catch (failure: unknown) {
      if (
        ["user_not_found", "email_already_verified"].includes(
          failureCode(failure),
        )
      ) {
        setEnterCode(true);
        setNotice(requestNotice);
      } else setError(recoveryErrorMessage(failure));
    } finally {
      setPending(false);
    }
  }

  async function finishSignOut() {
    setPending(true);
    setError(null);
    try {
      requireSuccess(await getNeonAuthClient().adapter.signOut({}));
      setSignedOut(true);
    } catch {
      setError(
        "Your password was updated, but sign-out could not be confirmed. Retry sign-out before returning.",
      );
    } finally {
      setPending(false);
    }
  }

  async function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || complete) return;
    if (!emailInput.current?.reportValidity()) return;
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the six-digit code from your email.");
      return;
    }
    if (recovering && password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      const otp = getNeonAuthClient().adapter.emailOtp;
      requireSuccess(
        recovering
          ? await otp.resetPassword({
              email: email.trim(),
              otp: code,
              password,
            })
          : await otp.verifyEmail({ email: email.trim(), otp: code }),
      );
      setComplete(true);
      setCode("");
      setPassword("");
      setConfirmation("");
      if (recovering) {
        requireSignIn("expired");
        await finishSignOut();
      }
    } catch (failure: unknown) {
      const invalid = [
        "invalid_otp",
        "otp_expired",
        "invalid_code",
        "otp_not_found",
        "too_many_attempts",
        "verification_code_not_found",
        "invalid_verification_code",
        "verification_code_expired",
      ].includes(failureCode(failure));
      setError(
        invalid
          ? "The code was not accepted or has expired. Request a new code and try again."
          : recoveryErrorMessage(failure),
      );
    } finally {
      setCode("");
      setPassword("");
      setConfirmation("");
      setPending(false);
    }
  }

  return (
    <section className="v2-auth-card" aria-labelledby="email-code-title">
      <p className="eyebrow">RouteValue account</p>
      <h2 id="email-code-title">
        {recovering ? "Reset your password" : "Verify your email"}
      </h2>
      {complete ? (
        <>
          <p role="status">
            {recovering
              ? "Your password was updated."
              : "Your email was verified."}{" "}
            {(!recovering || signedOut) && "Return to sign in."}
          </p>
          {recovering && !signedOut && (
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
        </>
      ) : (
        <>
          <p className="muted">
            {recovering
              ? "Request a password-reset code, then enter it here with your new password."
              : "This verifies your email and may sign you in; it does not change your password. Enter your email code here, or request a new one below. To reset your password, return to sign in and choose Forgot password?"}
          </p>
          <form className="v2-auth-form" onSubmit={requestCode}>
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                ref={emailInput}
                autoComplete="email"
                required
                value={email}
                disabled={pending}
                onChange={(event) => {
                  setEmail(event.target.value);
                  setCode("");
                  setPassword("");
                  setConfirmation("");
                  setNotice(null);
                }}
              />
            </label>
            <button
              className="v2-secondary-button"
              type="submit"
              disabled={pending}
            >
              {recovering ? "Send reset email" : "Send verification email"}
            </button>
          </form>
          {enterCode ? (
            <form className="v2-auth-form" onSubmit={submitCode}>
              <label className="field">
                <span>Email code</span>
                <input
                  type="text"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  minLength={6}
                  maxLength={6}
                  required
                  disabled={pending}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </label>
              {recovering && (
                <>
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
                </>
              )}
              <button
                className="v2-primary-button"
                type="submit"
                disabled={pending || !email.trim()}
              >
                {pending
                  ? "Please wait..."
                  : recovering
                    ? "Update password"
                    : "Verify email"}
              </button>
            </form>
          ) : (
            <p className="v2-auth-switch">
              <button
                type="button"
                disabled={pending}
                onClick={() => setEnterCode(true)}
              >
                I already have a reset code
              </button>
            </p>
          )}
        </>
      )}
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
      {(!complete || !recovering || signedOut) && (
        <p className="v2-auth-switch">
          <button
            type="button"
            disabled={pending}
            onClick={() => onBack(email.trim())}
          >
            I have an account
          </button>
        </p>
      )}
    </section>
  );
}
