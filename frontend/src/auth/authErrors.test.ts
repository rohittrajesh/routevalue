import { describe, expect, it } from "vitest";
import { authErrorMessage } from "./authErrors";

describe("safe auth failure messages", () => {
  it.each([
    ["invalid_credentials", 401, "email or password was not accepted"],
    ["EMAIL_NOT_VERIFIED", 403, "Verify your email"],
    ["user_already_exists", 409, "already exists"],
    ["INVALID_ORIGIN", 403, "app address"],
    ["SIGNUP_DISABLED", 403, "registration is disabled"],
    ["weak_password", 400, "stronger password"],
    ["over_request_rate_limit", 429, "Too many"],
    ["internal_error", 503, "Could not reach"],
  ])(
    "classifies %s without exposing provider details",
    (code, status, expected) => {
      const message = authErrorMessage(
        { code, status, message: "private-provider-data" },
        false,
      );
      expect(message).toContain(expected);
      expect(message).not.toContain("private-provider-data");
    },
  );
  it("handles network rejection", () => {
    expect(authErrorMessage(new TypeError("Failed to fetch"), false)).toContain(
      "Could not reach",
    );
  });
  it("recognizes the SDK-normalized invalid-origin error", () => {
    expect(
      authErrorMessage(
        {
          status: 403,
          code: "feature_not_supported",
          message: "Invalid origin",
        },
        false,
      ),
    ).toContain("use localhost");
  });
});
