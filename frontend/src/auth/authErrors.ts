/** Safe, actionable auth errors. Never render provider messages or request data. */
export function authErrorMessage(error: unknown, registering: boolean): string {
  const record = typeof error === "object" && error !== null ? error : {};
  const code =
    "code" in record && typeof record.code === "string"
      ? record.code.toLowerCase()
      : "";
  const status =
    "status" in record && typeof record.status === "number"
      ? record.status
      : null;
  // The Neon SDK normalizes unknown HTTP 403 codes to feature_not_supported,
  // while preserving the provider message. Classify only this known value;
  // never display arbitrary messages, emails, or request details.
  const invalidOrigin =
    "message" in record && record.message === "Invalid origin";

  if (
    [
      "invalid_credentials",
      "invalid_email_or_password",
      "user_not_found",
    ].includes(code)
  ) {
    return "Sign-in failed. The email or password was not accepted. Check that you are using your RouteValue development account.";
  }
  if (
    [
      "user_already_exists",
      "email_exists",
      "user_already_exists_use_another_email",
    ].includes(code)
  ) {
    return "An account with this email already exists. Switch to sign in.";
  }
  if (["email_not_confirmed", "email_not_verified"].includes(code)) {
    return "Verify your email before signing in. Check your inbox for the verification message.";
  }
  if (
    invalidOrigin ||
    ["invalid_origin", "invalid_callback_url"].includes(code)
  ) {
    return "Authentication is not configured to allow this app address. For local development, use localhost instead of 127.0.0.1.";
  }
  if (
    ["signup_disabled", "sign_up_disabled", "email_password_disabled"].includes(
      code,
    )
  ) {
    return "Email and password registration is disabled in the authentication service. Contact the app administrator.";
  }
  if (
    ["weak_password", "password_too_short", "password_too_long"].includes(code)
  ) {
    return "The password does not meet the authentication service requirements. Use a stronger password with at least eight characters.";
  }
  if (
    status === 429 ||
    ["over_request_rate_limit", "over_email_send_rate_limit"].includes(code)
  ) {
    return "Too many authentication attempts. Wait a few minutes before trying again.";
  }
  if (error instanceof TypeError || (status !== null && status >= 500)) {
    return "Could not reach the authentication service. Check your connection and try again. Browser privacy settings may also block the session.";
  }
  if (status === 403) {
    return "The authentication service rejected this request. Check whether your email needs verification or this app address is allowed.";
  }
  return registering
    ? "Account creation failed. Check your information and try again."
    : "Sign-in failed. Check your credentials and try again.";
}

/** Recovery never exposes whether an account exists or raw provider details. */
export function recoveryErrorMessage(error: unknown): string {
  const record = typeof error === "object" && error !== null ? error : {};
  if ("status" in record && record.status === 429) {
    return "Too many requests. Wait a few minutes before trying again.";
  }
  return "The authentication request could not be completed. Retry, or request a new email if the link expired. Contact the app administrator if this continues.";
}
