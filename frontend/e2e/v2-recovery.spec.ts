import { expect, test } from "@playwright/test";

test("requests reset and verification messages, then returns to sign in", async ({
  page,
}) => {
  await page.goto("/v2");
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page.getByRole("button", { name: "Send reset email" }).click();
  await expect(page.getByRole("status")).toContainText(
    "If this account is eligible",
  );
  await page.getByRole("button", { name: "I have an account" }).click();
  await page.getByRole("button", { name: "Resend verification email" }).click();
  await page.getByRole("button", { name: "Send verification email" }).click();
  await expect(page.getByRole("status")).toContainText(
    "If this account is eligible",
  );
  await expect(page.getByText("Profile connected.")).toHaveCount(0);
});

test("reset links clear URL secrets, require matching passwords, and return signed out", async ({
  page,
}) => {
  await page.goto("/v2/reset-password?token=browser-test-reset-token");
  await expect(
    page.getByRole("heading", { name: "Reset your password" }),
  ).toBeVisible();
  await expect(page).toHaveURL("/v2/reset-password");
  await page
    .getByLabel("New password", { exact: true })
    .fill("synthetic-password");
  await page.getByLabel("Confirm new password").fill("different-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("alert")).toContainText("do not match");
  await page.getByLabel("Confirm new password").fill("synthetic-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Your password was updated",
  );
  await page.getByRole("link", { name: "Return to sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
});

test("expired links cannot report success and reloading cannot reuse a consumed URL", async ({
  page,
}) => {
  await page.goto("/v2/reset-password?token=expired-browser-test-token");
  await page
    .getByLabel("New password", { exact: true })
    .fill("synthetic-password");
  await page.getByLabel("Confirm new password").fill("synthetic-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("alert")).toContainText("request a new email");
  await expect(page.getByLabel("New password", { exact: true })).toHaveValue(
    "",
  );
  await expect(page.getByRole("status")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("missing or invalid");
  await expect(
    page.getByRole("button", { name: "Update password" }),
  ).toHaveCount(0);
});

test("verification codes confirm email while reset codes require a new password", async ({
  page,
}) => {
  await page.goto("/v2");
  await page.getByRole("button", { name: "Resend verification email" }).click();
  await expect(page.getByText(/does not change your password/)).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page.getByLabel("Email code").fill("000000");
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Your email was verified",
  );
  await page.getByRole("button", { name: "I have an account" }).click();
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await page.getByRole("button", { name: "Send reset email" }).click();
  await expect(page.getByLabel("Email code")).toBeVisible();
  await page.getByLabel("Email code").fill("000000");
  await page
    .getByLabel("New password", { exact: true })
    .fill("synthetic-password");
  await page.getByLabel("Confirm new password").fill("different-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("alert")).toContainText("do not match");
  await page.getByLabel("Confirm new password").fill("synthetic-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Your password was updated",
  );
  await page.getByRole("button", { name: "I have an account" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
});

test("new registration opens verification code entry and expired codes allow resend", async ({
  page,
}) => {
  await page.goto("/v2");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Browser fixture");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Verify your email" }),
  ).toBeVisible();
  await page.getByLabel("Email code").fill("111111");
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "not accepted or has expired",
  );
  await expect(page.getByLabel("Email code")).toHaveValue("");
  await page.getByRole("button", { name: "Send verification email" }).click();
  await expect(page.getByRole("status")).toContainText(
    "If this account is eligible",
  );
  await page.getByLabel("Email code").fill("000000");
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "Your email was verified",
  );
});
