import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript((id) => {
    // Keep this test's identity across reloads, isolated from other tests.
    if (!localStorage.getItem("browser-test-user"))
      localStorage.setItem("browser-test-user", id);
  }, randomUUID());
  await page.goto("/v2");
  await expect(page.getByText("Profile connected.")).toBeVisible();
});

async function addVehicle(page: Page, model: "Gasoline" | "Electric") {
  await page
    .getByRole("combobox", { name: "Model year", exact: true })
    .selectOption("2025");
  await page
    .getByRole("combobox", { name: "Make", exact: true })
    .selectOption("Example");
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption(model);
  await page
    .getByRole("combobox", { name: "Configuration", exact: true })
    .selectOption(model);
  await page.getByRole("button", { name: "Save vehicle", exact: true }).click();
  const vehicle = page
    .getByRole("region", { name: "Saved vehicles", exact: true })
    .getByRole("list")
    .getByRole("listitem")
    .filter({ hasText: `2025 Example ${model}` });
  await expect(vehicle).toBeVisible();
  return vehicle;
}

async function configure(
  page: Page,
  model: "Gasoline" | "Electric" = "Gasoline",
) {
  await page.getByLabel("Value of time ($/hour)").fill("24");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Value of time saved.")).toBeVisible();
  const vehicle = await addVehicle(page, model);
  await vehicle.getByRole("button", { name: "Set as default" }).click();
  await expect(vehicle.getByText("Default", { exact: true })).toBeVisible();
  return vehicle;
}

async function locations(page: Page) {
  await page
    .getByRole("combobox", { name: "Origin", exact: true })
    .fill("UC San");
  await page.getByRole("button", { name: /UC San Diego/ }).click();
  await page
    .getByRole("combobox", { name: "Destination", exact: true })
    .fill("Balboa");
  await page.getByRole("button", { name: /Balboa Park/ }).click();
}

async function compare(page: Page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v2/trip-evaluations") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Compare routes", exact: true })
    .click();
  return response;
}

test("gasoline onboarding, automatic pricing, mass add/clear and real API terrain calculations", async ({
  page,
}) => {
  const vehicle = await configure(page);
  await locations(page);
  const baselineResponse = await compare(page);
  expect(baselineResponse.status()).toBe(200);
  const baseline = await baselineResponse.json();
  expect(baseline.energy_price).toMatchObject({
    source: "regional_market",
    provider: "EIA",
  });
  await expect(
    page.getByRole("heading", { name: "Baseline energy estimates used" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Energy price used" }),
  ).toContainText("EIA");
  expect(baselineResponse.request().postDataJSON()).not.toHaveProperty(
    "gasoline",
  );

  await vehicle.getByRole("button", { name: "Add vehicle weight" }).click();
  await vehicle.getByLabel("Curb weight", { exact: true }).fill("1800");
  await vehicle
    .getByRole("combobox", { name: "Unit", exact: true })
    .selectOption("kg");
  await vehicle
    .getByLabel("Weight source", { exact: true })
    .fill("Synthetic browser fixture");
  await vehicle.getByRole("button", { name: "Save vehicle weight" }).click();
  await expect(vehicle.getByText("Vehicle mass saved.")).toBeVisible();
  // Saved personalization changed: old results must disappear, locations stay.
  await expect(
    page.getByRole("heading", { name: "Your route comparison" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Origin", exact: true }),
  ).toHaveValue("UC San Diego, La Jolla, CA");
  const adjusted = await (await compare(page)).json();
  expect(adjusted.terrain_status.terrain_applied).toBe(true);
  expect(
    Number(adjusted.route_evaluations[0].energy_estimate.cost),
  ).toBeGreaterThan(Number(baseline.route_evaluations[0].energy_estimate.cost));
  await expect(
    page.getByRole("heading", { name: "Terrain adjustments applied" }),
  ).toBeVisible();
  await expect(
    page.locator('.route-map-canvas[data-e2e-map-ready="true"]'),
  ).toBeVisible();

  await vehicle.getByRole("button", { name: "Clear vehicle weight" }).click();
  await vehicle.getByRole("button", { name: "Confirm clear" }).click();
  await expect(vehicle.getByText("Vehicle mass cleared.")).toBeVisible();
  const cleared = await (await compare(page)).json();
  expect(cleared).toEqual(baseline);
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Vehicle for this trip" }),
  ).toContainText("(default)");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("automatic pricing failure retains trip and manual override succeeds", async ({
  page,
  context,
}) => {
  await configure(page);
  await locations(page);
  await context.addCookies([
    { name: "fixture_price", value: "missing", url: "http://127.0.0.1:4173" },
  ]);
  expect((await compare(page)).status()).toBe(409);
  await page.getByRole("button", { name: "Use manual gasoline price" }).click();
  await page.getByLabel("Gasoline price ($/gallon)").fill("5.125");
  const response = await compare(page);
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON().gasoline.fuel_price_per_gallon).toBe(
    "5.125",
  );
  await expect(
    page.getByText("Manual gasoline price supplied for this trip."),
  ).toBeVisible();
});

test("EV selection, terrain fallback, preference invalidation and delete/default cleanup", async ({
  page,
  context,
}) => {
  const vehicle = await configure(page, "Electric");
  await locations(page);
  await page.getByRole("radio", { name: "Enter a rate for this trip" }).check();
  await page.getByLabel("Electricity price ($/kWh)").fill("0.275");
  await context.addCookies([
    { name: "fixture_terrain", value: "missing", url: "http://127.0.0.1:4173" },
  ]);
  const response = await compare(page);
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.energy_price).toMatchObject({
    energy_type: "electricity",
    price_per_kilowatt_hour: "0.275",
  });
  expect(result.terrain_status.fallback_reasons).toContain(
    "elevation_unavailable",
  );
  await expect(
    page.getByText("Your electricity rate supplied for this trip."),
  ).toBeVisible();
  await expect(page.getByText(/Energy used: .* kWh/).first()).toBeVisible();
  await page.getByLabel("Value of time ($/hour)").fill("30");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Value of time saved.")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your route comparison" }),
  ).toHaveCount(0);
  await vehicle
    .getByRole("button", { name: "Delete 2025 Example Electric" })
    .click();
  await vehicle.getByRole("button", { name: "Confirm delete" }).click();
  await expect(
    page.getByRole("button", { name: "Compare routes", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("Save a vehicle in your garage before comparing routes."),
  ).toBeVisible();
});

test("saved EV rate survives reload, drives trips, permits override and clears safely", async ({
  page,
}, testInfo) => {
  await configure(page, "Electric");
  await page.getByLabel("Saved electricity rate ($/kWh)").fill("0.2875");
  await page
    .getByRole("button", { name: "Save electricity rate", exact: true })
    .click();
  await expect(
    page.getByText("Electricity rate saved.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Saved electricity rate ($/kWh)")).toHaveValue(
    "0.2875",
  );
  await page
    .getByRole("region", { name: "Energy preferences", exact: true })
    .screenshot({ path: testInfo.outputPath("energy-preferences.png") });
  await locations(page);
  const savedResponse = await compare(page);
  expect(savedResponse.status()).toBe(200);
  expect(savedResponse.request().postDataJSON()).not.toHaveProperty(
    "electricity",
  );
  expect((await savedResponse.json()).energy_price).toMatchObject({
    source: "user_preference",
    price_per_kilowatt_hour: "0.2875",
  });
  await expect(
    page.getByText("Your saved electricity rate.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("radio", { name: "Enter a rate for this trip" }).check();
  await page.getByLabel("Electricity price ($/kWh)", { exact: true }).fill("0");
  const override = await compare(page);
  expect((await override.json()).energy_price).toMatchObject({
    source: "user_input",
    price_per_kilowatt_hour: "0",
  });
  await expect(page.getByLabel("Saved electricity rate ($/kWh)")).toHaveValue(
    "0.2875",
  );
  await page.getByRole("radio", { name: "Use saved electricity rate" }).check();
  await page.getByLabel("Saved electricity rate ($/kWh)").fill("");
  await page
    .getByRole("button", { name: "Save electricity rate", exact: true })
    .click();
  await expect(
    page.getByText("Electricity rate cleared.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your route comparison" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Compare routes", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("combobox", { name: "Origin", exact: true }),
  ).toHaveValue("UC San Diego, La Jolla, CA");
});

test("preferred market survives reload and clearing restores trip-origin pricing", async ({
  page,
}) => {
  await configure(page);
  await locations(page);
  const initial = await compare(page);
  expect((await initial.json()).energy_price.price_per_gallon).toBe("4.125");
  await page
    .getByRole("combobox", { name: "Fuel purchasing area", exact: true })
    .fill("Raleigh");
  await page.getByRole("button", { name: /Raleigh/ }).click();
  await page
    .getByRole("button", { name: "Save fuel market", exact: true })
    .click();
  await expect(
    page.getByText("Fuel market saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your route comparison" }),
  ).toHaveCount(0);
  const preferred = await compare(page);
  expect(preferred.request().postDataJSON().origin.display_name).toBe(
    "UC San Diego, La Jolla, CA",
  );
  expect((await preferred.json()).energy_price.price_per_gallon).toBe("3.125");
  await page.reload();
  await expect(
    page.getByText("Fuel market: Raleigh, NC", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Value of time ($/hour)").fill("30");
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(
    page.getByText("Value of time saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Fuel market: Raleigh, NC", { exact: true }),
  ).toBeVisible();
  await locations(page);
  await page
    .getByRole("button", { name: "Clear fuel market", exact: true })
    .click();
  await expect(
    page.getByText(
      "Fuel market cleared. Automatic pricing will use the trip origin.",
    ),
  ).toBeVisible();
  const cleared = await compare(page);
  expect((await cleared.json()).energy_price.price_per_gallon).toBe("4.125");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
