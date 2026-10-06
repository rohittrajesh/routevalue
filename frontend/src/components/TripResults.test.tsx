import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  ResolvedLocationInput,
  RouteEvaluationResponse,
  TripEvaluationResponse,
} from "../types/api";

import TripResults from "./TripResults";

vi.mock("./RouteMap", () => ({
  default: ({
    recommendedRouteIndex,
    selectedRouteIndex,
    origin,
    destination,
  }: {
    routeEvaluations: RouteEvaluationResponse[];
    recommendedRouteIndex: number;
    selectedRouteIndex?: number | null;
    origin: ResolvedLocationInput;
    destination: ResolvedLocationInput;
  }) => (
    <div data-testid="route-map">
      <span>Recommended index: {recommendedRouteIndex}</span>
      <span>
        Selected index:{" "}
        {selectedRouteIndex === null || selectedRouteIndex === undefined
          ? "none"
          : selectedRouteIndex}
      </span>
      <span>Map origin: {origin.display_name}</span>
      <span>Map destination: {destination.display_name}</span>
    </div>
  ),
}));

const origin: ResolvedLocationInput = {
  display_name: "Origin Place",
  latitude: 32.88,
  longitude: -117.23,
  source: "google_places",
  source_id: "origin-place-id",
};

const destination: ResolvedLocationInput = {
  display_name: "Destination Place",
  latitude: 32.73,
  longitude: -117.19,
  source: "google_places",
  source_id: "destination-place-id",
};

const successfulResult: TripEvaluationResponse = {
  route_evaluations: [
    {
      route: {
        distance_meters: 20_400,
        duration_seconds: 1_020,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.78",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.78",
        time_cost: "7.06",
        generalized_cost: "9.85",
      },
      geometry: {
        points: [
          {
            latitude: 32.88,
            longitude: -117.23,
          },
          {
            latitude: 32.8,
            longitude: -117.2,
          },
        ],
      },
    },
    {
      route: {
        distance_meters: 24_100,
        duration_seconds: 1_260,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "3.29",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "3.29",
        time_cost: "8.81",
        generalized_cost: "12.10",
      },
      geometry: {
        points: [
          {
            latitude: 32.88,
            longitude: -117.23,
          },
          {
            latitude: 32.75,
            longitude: -117.1,
          },
        ],
      },
    },
  ],
  decision: {
    recommended_route: {
      distance_meters: 20_400,
      duration_seconds: 1_020,
      toll_cost: "0",
    },
    reason: "faster_and_cheaper",
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 2,
    eligible_count: 2,
  },
};

describe("TripResults", () => {
  it("renders personalized costs from the API response", () => {
    render(
      <TripResults
        result={successfulResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(screen.getAllByText("$9.85").length).toBeGreaterThan(0);
    expect(screen.getByText("$12.10")).toBeInTheDocument();

    expect(screen.getAllByText("Value of travel time")).toHaveLength(2);
  });

  it("marks the backend-recommended route as the best match", () => {
    render(
      <TripResults
        result={successfulResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(
      screen.getByRole("article", {
        name: /route 1, recommended/i,
      }),
    ).toBeInTheDocument();

    expect(screen.getByText(/route 1 is your best match/i)).toBeInTheDocument();

    expect(
      screen.getByText(
        /faster and cheaper than the next-best personalized-cost alternative/i,
      ),
    ).toBeInTheDocument();
  });

  it("passes the resolved trip endpoints to the route map", () => {
    render(
      <TripResults
        result={successfulResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(screen.getByText("Map origin: Origin Place")).toBeInTheDocument();

    expect(
      screen.getByText("Map destination: Destination Place"),
    ).toBeInTheDocument();
  });

  it("renders an unavailable state for an ineligible route", () => {
    const unavailableResult: TripEvaluationResponse = {
      route_evaluations: [
        {
          route: {
            distance_meters: 10_000,
            duration_seconds: 900,
            toll_cost: null,
          },
          energy_estimate: {
            cost: "2.00",
          },
          eligibility: {
            eligible: false,
            reason: "missing_toll_cost",
          },
          cost_breakdown: null,
          geometry: null,
        },
      ],
      decision: {
        recommended_route: null,
        reason: null,
        numerical_tie: false,
        missing_data_present: true,
        candidate_count: 1,
        eligible_count: 0,
      },
    };

    render(
      <TripResults
        result={unavailableResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(screen.getByText(/unable to score this route/i)).toBeInTheDocument();

    expect(
      screen.getByText(/toll information is unavailable/i),
    ).toBeInTheDocument();

    expect(screen.getByText("No recommendation available")).toBeInTheDocument();

    expect(
      screen.getByText(
        /RouteValue found routes, but does not have enough data to score them/i,
      ),
    ).toBeInTheDocument();

    expect(screen.getByTestId("route-map")).toBeInTheDocument();
  });

  it("lets the user inspect a different route without changing the recommendation", async () => {
    const user = userEvent.setup();

    render(
      <TripResults
        result={successfulResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(screen.getByText("Recommended index: 0")).toBeInTheDocument();
    expect(screen.getByText("Selected index: none")).toBeInTheDocument();

    const routeButtons = screen.getAllByRole("button", {
      name: /view on map/i,
    });

    await user.click(routeButtons[1]);

    expect(screen.getByText("Recommended index: 0")).toBeInTheDocument();
    expect(screen.getByText("Selected index: 1")).toBeInTheDocument();

    expect(
      screen.getByRole("article", {
        name: /route 2, selected for map inspection/i,
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("article", {
        name: /route 1, recommended/i,
      }),
    ).toBeInTheDocument();
  });

  it("renders a dedicated empty state when no routes are found", () => {
    const emptyResult: TripEvaluationResponse = {
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

    render(
      <TripResults
        result={emptyResult}
        origin={origin}
        destination={destination}
      />,
    );

    expect(screen.getByText("No routes found")).toBeInTheDocument();

    expect(
      screen.getByText(
        /RouteValue couldn't find a route between these locations/i,
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Try a different origin or destination/i),
    ).toBeInTheDocument();

    expect(screen.queryByTestId("route-map")).not.toBeInTheDocument();

    expect(screen.queryByRole("article")).not.toBeInTheDocument();

    expect(
      screen.queryByText(/does not have enough data to score/i),
    ).not.toBeInTheDocument();
  });

  it("can clear the currently inspected route", async () => {
    const user = userEvent.setup();

    render(
      <TripResults
        result={successfulResult}
        origin={origin}
        destination={destination}
      />,
    );

    const routeButtons = screen.getAllByRole("button", {
      name: /view on map/i,
    });

    await user.click(routeButtons[1]);

    expect(screen.getByText("Selected index: 1")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: /viewing on map/i,
      }),
    );

    expect(screen.getByText("Selected index: none")).toBeInTheDocument();
    expect(screen.getByText("Recommended index: 0")).toBeInTheDocument();
  });
});
