import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  ResolvedLocationInput,
  V2TripEvaluationResponse,
} from "../types/api";
import V2TripResults from "./V2TripResults";

vi.mock("./RouteMap", () => ({
  default: ({
    recommendedRouteIndex,
    selectedRouteIndex,
    routeEvaluations,
  }: {
    recommendedRouteIndex: number;
    selectedRouteIndex: number | null;
    routeEvaluations: V2TripEvaluationResponse["route_evaluations"];
  }) => (
    <div data-testid="route-map-mock">
      Recommended index: {recommendedRouteIndex}; Selected index:{" "}
      {selectedRouteIndex === null ? "all" : selectedRouteIndex}; Routes:{" "}
      {routeEvaluations.length}
    </div>
  ),
}));

const origin: ResolvedLocationInput = {
  display_name: "Origin",
  latitude: 32.88,
  longitude: -117.23,
};

const destination: ResolvedLocationInput = {
  display_name: "Destination",
  latitude: 32.73,
  longitude: -117.19,
};

const gasolineResult: V2TripEvaluationResponse = {
  route_evaluations: [
    {
      route: {
        distance_meters: 10000,
        duration_seconds: 900,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.00",
        consumption: {
          energy_type: "gasoline",
          gallons: "0.75",
        },
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.00",
        time_cost: "5.00",
        generalized_cost: "7.00",
      },
      geometry: {
        points: [
          { latitude: 32.88, longitude: -117.23 },
          { latitude: 32.73, longitude: -117.19 },
        ],
      },
    },
    {
      route: {
        distance_meters: 12000,
        duration_seconds: 800,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "3.00",
        consumption: {
          energy_type: "gasoline",
          gallons: "1.00",
        },
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "3.00",
        time_cost: "4.50",
        generalized_cost: "7.50",
      },
      geometry: {
        points: [
          { latitude: 32.88, longitude: -117.23 },
          { latitude: 32.75, longitude: -117.1 },
        ],
      },
    },
  ],
  decision: {
    recommended_route: {
      distance_meters: 10000,
      duration_seconds: 900,
      toll_cost: "0",
    },
    reason: "faster_and_cheaper",
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 2,
    eligible_count: 2,
  },
};

describe("V2TripResults", () => {
  it("passes evaluated routes and recommendation to the map", () => {
    render(
      <V2TripResults
        result={gasolineResult}
        origin={origin}
        destination={destination}
        evaluatedVehicleName="2023 Toyota Camry"
      />,
    );

    expect(screen.getByTestId("route-map-mock")).toHaveTextContent(
      "Recommended index: 0",
    );
    expect(screen.getByTestId("route-map-mock")).toHaveTextContent("Routes: 2");
    expect(
      screen.getByText(/Evaluated with 2023 Toyota Camry/),
    ).toBeInTheDocument();
    expect(screen.getByText("Best match")).toBeInTheDocument();
    expect(screen.getByText("Energy used: 0.75 gal")).toBeInTheDocument();
  });

  it("selects an alternative route and restores all routes", async () => {
    const user = userEvent.setup();

    render(
      <V2TripResults
        result={gasolineResult}
        origin={origin}
        destination={destination}
        evaluatedVehicleName="2023 Toyota Camry"
      />,
    );

    const routeTwoButton = screen.getByRole("button", {
      name: "View Route 2 on map",
    });

    await user.click(routeTwoButton);

    expect(routeTwoButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("route-map-mock")).toHaveTextContent(
      "Selected index: 1",
    );

    await user.click(routeTwoButton);

    expect(routeTwoButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("route-map-mock")).toHaveTextContent(
      "Selected index: all",
    );
  });

  it("preserves route comparison when geometry is missing", () => {
    const result: V2TripEvaluationResponse = {
      ...gasolineResult,
      route_evaluations: gasolineResult.route_evaluations.map((evaluation) => ({
        ...evaluation,
        geometry: null,
      })),
    };

    render(
      <V2TripResults
        result={result}
        origin={origin}
        destination={destination}
        evaluatedVehicleName="2023 Toyota Camry"
      />,
    );

    expect(screen.getByText("Best match")).toBeInTheDocument();
    expect(screen.getByTestId("route-map-mock")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "View Route 1 on map" }),
    ).not.toBeInTheDocument();
  });

  it("renders electric consumption in kWh", () => {
    const result: V2TripEvaluationResponse = {
      ...gasolineResult,
      route_evaluations: [
        {
          ...gasolineResult.route_evaluations[0],
          energy_estimate: {
            cost: "10.28",
            consumption: {
              energy_type: "electricity",
              kilowatt_hours: "20.56",
            },
          },
        },
      ],
      decision: {
        ...gasolineResult.decision,
        candidate_count: 1,
        eligible_count: 1,
      },
    };

    render(
      <V2TripResults
        result={result}
        origin={origin}
        destination={destination}
        evaluatedVehicleName="2024 Tesla Model Y"
      />,
    );

    expect(screen.getByText("Energy used: 20.56 kWh")).toBeInTheDocument();
    expect(screen.getByText("$10.28")).toBeInTheDocument();
  });
});
