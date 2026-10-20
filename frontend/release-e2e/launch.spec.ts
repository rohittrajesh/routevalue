import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("https://auth.example.invalid/**", (route) =>
    route.fulfill({ json: null }),
  );
  await page.route("https://api.example.invalid/**", (route) =>
    route.fulfill({
      status: 503,
      json: {
        code: "service_unavailable",
        detail: "Synthetic release-test upstream",
      },
    }),
  );
  await page.route("https://maps.googleapis.com/**", (route) => route.abort());
});

test("the production V2 bundle loads at root, survives reload and retains /v2", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Know the cost. Choose what matters.",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Forgot password?" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".rv-logo")
        .evaluate(
          (node) =>
            node instanceof HTMLImageElement &&
            node.complete &&
            node.naturalWidth > 0,
        ),
    )
    .toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("sign-in.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.goto("/v2");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
});

test("the same production bundle preserves the V1 planner at /v1", async ({
  page,
}) => {
  await page.goto("/v1");
  await expect(
    page.getByRole("heading", {
      name: "Choose the route that costs you less.",
    }),
  ).toBeVisible();
});

test("direct reset links receive the SPA and strip the token before form submission", async ({
  page,
}) => {
  const response = await page.goto(
    "/v2/reset-password?token=synthetic-release-token",
  );
  expect(response?.status()).toBe(200);
  await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
  await expect(page).toHaveURL("/v2/reset-password");
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("missing or invalid");
});

test("the production SDK uses OTP recovery and reports rejected codes honestly", async ({
  page,
}) => {
  await page.route("**/email-otp/request-password-reset", (route) =>
    route.fulfill({ json: { success: true } }),
  );
  await page.route("**/email-otp/reset-password", (route) =>
    route.fulfill({
      status: 400,
      json: { code: "INVALID_OTP", message: "Invalid OTP" },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await page
    .getByLabel("Email", { exact: true })
    .fill("release-fixture@example.test");
  const requested = page.waitForRequest("**/email-otp/request-password-reset");
  await page.getByRole("button", { name: "Send reset email" }).click();
  expect((await requested).postDataJSON()).toEqual({
    email: "release-fixture@example.test",
  });
  await page.getByLabel("Email code").fill("000000");
  await page
    .getByLabel("New password", { exact: true })
    .fill("synthetic-release-password");
  await page
    .getByLabel("Confirm new password")
    .fill("synthetic-release-password");
  const submitted = page.waitForRequest("**/email-otp/reset-password");
  await page.getByRole("button", { name: "Update password" }).click();
  expect((await submitted).postDataJSON()).toEqual({
    email: "release-fixture@example.test",
    otp: "000000",
    password: "synthetic-release-password",
  });
  await expect(page.getByRole("alert")).toContainText(
    "not accepted or has expired",
  );
});
