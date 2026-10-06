import { expect, test, type Page } from "@playwright/test";

const successfulEvaluation = {
  route_evaluations: [
    {
      route: {
        distance_meters: 18_200,
        duration_seconds: 1_080,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.73",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.73",
        time_cost: "6.00",
        generalized_cost: "8.73",
      },
      geometry: {
        points: [
          {
            latitude: 32.8801,
            longitude: -117.234,
          },
          {
            latitude: 32.7341,
            longitude: -117.1446,
          },
        ],
      },
    },
    {
      route: {
        distance_meters: 20_600,
        duration_seconds: 1_200,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "3.09",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "3.09",
        time_cost: "6.67",
        generalized_cost: "9.76",
      },
      geometry: {
        points: [
          {
            latitude: 32.8801,
            longitude: -117.234,
          },
          {
            latitude: 32.8,
            longitude: -117.19,
          },
          {
            latitude: 32.7341,
            longitude: -117.1446,
          },
        ],
      },
    },
  ],
  decision: {
    recommended_route: {
      distance_meters: 18_200,
      duration_seconds: 1_080,
      toll_cost: "0",
    },
    reason: "faster_and_cheaper",
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 2,
    eligible_count: 2,
  },
};

const zeroRouteEvaluation = {
  route_evaluations: [],
  decision: {
    recommended_route: null,
    reason: null,
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 0,
    eligible_count: 0,
  },
};

async function fillTripForm(page: Page) {
  const origin = page.getByRole("combobox", {
    name: "Origin",
  });

  await origin.fill("UC San");

  await page
    .getByRole("button", {
      name: /UC San Diego/i,
    })
    .click();

  const destination = page.getByRole("combobox", {
    name: "Destination",
  });

  await destination.fill("Balboa");

  await page
    .getByRole("button", {
      name: /Balboa Park/i,
    })
    .click();

  await page.getByLabel(/value of time/i).fill("20");
  await page.getByLabel(/fuel efficiency/i).fill("30");
  await page.getByLabel(/gas price/i).fill("4.50");
}

async function submitTrip(page: Page) {
  await page
    .getByRole("button", {
      name: "Compare routes",
    })
    .click();
}

test("evaluates a resolved trip and renders the recommendation", async ({
  page,
}) => {
  let submittedRequest: unknown = null;

  await page.route("**/api/trip-evaluations", async (route) => {
    submittedRequest = route.request().postDataJSON();

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successfulEvaluation),
    });
  });

  await page.goto("/");

  await fillTripForm(page);
  await submitTrip(page);

  await expect(page.getByText(/Route 1 is your best match/i)).toBeVisible();

  await expect(
    page.getByRole("article", {
      name: /Route 1, recommended/i,
    }),
  ).toBeVisible();

  await expect(
    page.getByRole("article", {
      name: /^Route 2$/i,
    }),
  ).toBeVisible();

  await expect(page.getByText("$8.73").first()).toBeVisible();

  await expect(
    page.locator('.route-map-canvas[data-e2e-map-ready="true"]'),
  ).toBeVisible();

  expect(submittedRequest).toMatchObject({
    origin: {
      display_name: "UC San Diego, La Jolla, CA",
      source: "google_places",
      source_id: "e2e-ucsd",
    },
    destination: {
      display_name: "Balboa Park, San Diego, CA",
      source: "google_places",
      source_id: "e2e-balboa",
    },
    value_of_time_per_hour: "20",
    gasoline: {
      fuel_efficiency_mpg: "30",
      fuel_grade: "regular",
      fuel_price_per_gallon: "4.50",
    },
  });
});

test("shows a routing outage and succeeds when the user retries", async ({
  page,
}) => {
  let requestCount = 0;

  await page.route("**/api/trip-evaluations", async (route) => {
    requestCount += 1;

    if (requestCount === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          code: "routing_service_unavailable",
          detail: "Routes are temporarily unavailable. Please try again.",
        }),
      });

      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successfulEvaluation),
    });
  });

  await page.goto("/");

  await fillTripForm(page);
  await submitTrip(page);

  const alert = page.getByRole("alert");

  await expect(alert).toContainText("RouteValue is temporarily unavailable.");

  await expect(alert).toContainText(
    "Routes are temporarily unavailable. Please try again.",
  );

  await expect(
    page.getByRole("combobox", {
      name: "Origin",
    }),
  ).toHaveValue("UC San Diego, La Jolla, CA");

  await expect(
    page.getByRole("combobox", {
      name: "Destination",
    }),
  ).toHaveValue("Balboa Park, San Diego, CA");

  await submitTrip(page);

  await expect(page.getByText(/Route 1 is your best match/i)).toBeVisible();

  await expect(page.getByRole("alert")).not.toBeVisible();

  expect(requestCount).toBe(2);
});

test("shows friendly validation feedback without exposing raw API details", async ({
  page,
}) => {
  await page.route("**/api/trip-evaluations", async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: [
          {
            type: "value_error",
            loc: ["body", "gasoline", "fuel_efficiency_mpg"],
            msg: "provider/internal validation detail",
            input: "-1",
          },
        ],
      }),
    });
  });

  await page.goto("/");

  await fillTripForm(page);
  await submitTrip(page);

  const alert = page.getByRole("alert");

  await expect(alert).toContainText("Check your trip information.");

  await expect(alert).toContainText(
    "Some trip information is invalid. Please check your inputs.",
  );

  await expect(alert).not.toContainText("provider/internal validation detail");

  await expect(page.getByText(/Route 1 is your best match/i)).not.toBeVisible();
});

test("renders a successful zero-route result as an empty state", async ({
  page,
}) => {
  await page.route("**/api/trip-evaluations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(zeroRouteEvaluation),
    });
  });

  await page.goto("/");

  await fillTripForm(page);
  await submitTrip(page);

  await expect(page.getByText("No routes found")).toBeVisible();

  await expect(
    page.getByText(/RouteValue couldn't find a route between these locations/i),
  ).toBeVisible();

  await expect(
    page.getByText(/Try a different origin or destination/i),
  ).toBeVisible();

  await expect(page.locator(".route-map-panel")).toHaveCount(0);

  await expect(page.getByRole("article")).toHaveCount(0);

  await expect(page.getByRole("alert")).toHaveCount(0);
});
