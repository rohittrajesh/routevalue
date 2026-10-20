import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript((id) => {
    if (!localStorage.getItem("browser-test-account")) {
      localStorage.setItem("browser-test-account", id);
      localStorage.setItem("browser-test-user", id);
    }
  }, randomUUID());
  await page.goto("/v2");
  await expect(page.getByText("Profile connected.")).toBeVisible();
  await page.getByLabel("Value of time ($/hour)").fill("24");
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(page.getByText("Value of time saved.")).toBeVisible();
});

async function signIn(page: Page) {
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Profile connected.")).toBeVisible();
  await expect(page.getByLabel("Value of time ($/hour)")).toHaveValue("24");
}

test("sign-out removes private state, stays signed out on reload, and sign-in restores preferences", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your RouteValue profile" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await signIn(page);
});

test("API expiry removes the workspace and permits same-account reauthentication", async ({
  page,
}) => {
  await page.route("**/api/v2/preferences", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 401,
        json: {
          code: "authentication_required",
          detail: "Authentication required.",
        },
      });
    } else await route.continue();
  });
  await page.getByLabel("Value of time ($/hour)").fill("99");
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(
    page.getByText("Your session has expired. Please sign in again.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Plan a trip" })).toHaveCount(
    0,
  );
  await page.unroute("**/api/v2/preferences");
  await signIn(page);
});

test("another tab changing account removes the previous user's preferences", async ({
  page,
  context,
}) => {
  const other = await context.newPage();
  await other.goto("/v2");
  await expect(other.getByText("Profile connected.")).toBeVisible();
  await other.evaluate(
    (id) => localStorage.setItem("browser-test-user", id),
    randomUUID(),
  );
  await expect(page.getByLabel("Value of time ($/hour)")).toHaveValue("");
  await expect(page.getByText("Profile connected.")).toBeVisible();
  await other.close();
});
