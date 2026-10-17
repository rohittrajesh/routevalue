import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  ResolvedLocationInput,
  V2TripEvaluationResponse,
} from "../types/api";
import V2TripResults from "./V2TripResults";

vi.mock("./RouteMap", () => ({
  default: () => <div data-testid="terrain-test-route-map" />,
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

const baseResult: V2TripEvaluationResponse = {
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
      geometry: null,
    },
    {
      route: {
        distance_meters: 12000,
        duration_seconds: 800,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.50",
        consumption: {
          energy_type: "gasoline",
          gallons: "0.90",
        },
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.50",
        time_cost: "4.50",
        generalized_cost: "7.00",
      },
      geometry: null,
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

function renderResult(result: V2TripEvaluationResponse) {
  return render(
    <V2TripResults
      result={result}
      origin={origin}
      destination={destination}
      evaluatedVehicleName="Test Vehicle"
    />,
  );
}

describe("V2 terrain status presentation", () => {
  it("does not infer terrain usage when diagnostics are absent", () => {
    renderResult(baseResult);

    expect(
      screen.getByRole("heading", {
        name: "Terrain status unavailable",
      }),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", {
        name: "Terrain adjustments applied",
      }),
    ).not.toBeInTheDocument();

    expect(screen.getByText("Energy used: 0.75 gal")).toBeInTheDocument();
  });

  it("reports disabled acquisition and baseline energy", () => {
    renderResult({
      ...baseResult,
      terrain_status: {
        terrain_applied: false,
        fallback_reasons: ["acquisition_disabled"],
        route_acquisition_statuses: ["unavailable", "unavailable"],
        route_coverage_fractions: [null, null],
      },
    });

    expect(
      screen.getByRole("heading", {
        name: "Baseline energy estimates used",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Elevation sampling is currently disabled/),
    ).toBeInTheDocument();

    expect(screen.getByTestId("terrain-test-route-map")).toBeInTheDocument();

    expect(screen.getAllByText(/Usable coverage: Not reported/)).toHaveLength(
      2,
    );
  });

  it("reports missing vehicle mass without hiding other reasons", () => {
    renderResult({
      ...baseResult,
      terrain_status: {
        terrain_applied: false,
        fallback_reasons: ["acquisition_disabled", "missing_vehicle_mass"],
        route_acquisition_statuses: ["unavailable", "unavailable"],
        route_coverage_fractions: [null, null],
      },
    });

    expect(
      screen.getByText(/Elevation sampling is currently disabled/),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/does not have verified mass data/),
    ).toBeInTheDocument();
  });

  it("reports genuine terrain application and route coverage", () => {
    renderResult({
      ...baseResult,
      terrain_status: {
        terrain_applied: true,
        fallback_reasons: [],
        route_acquisition_statuses: ["complete", "partial"],
        route_coverage_fractions: ["1", "0.86"],
      },
    });

    expect(
      screen.getByRole("heading", {
        name: "Terrain adjustments applied",
      }),
    ).toBeInTheDocument();

    expect(screen.getByText(/Usable coverage: 100%/)).toBeInTheDocument();

    expect(screen.getByText(/Usable coverage: 86%/)).toBeInTheDocument();

    expect(screen.getByText(/Elevation: Complete/)).toBeInTheDocument();

    expect(screen.getByText(/Elevation: Partial/)).toBeInTheDocument();
  });

  it("does not claim terrain was applied just because elevation exists", () => {
    renderResult({
      ...baseResult,
      terrain_status: {
        terrain_applied: false,
        fallback_reasons: ["untrusted_geometry"],
        route_acquisition_statuses: ["complete", "complete"],
        route_coverage_fractions: ["1", "1"],
      },
    });

    expect(
      screen.getByRole("heading", {
        name: "Baseline energy estimates used",
      }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/route geometry was not reliable enough/),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", {
        name: "Terrain adjustments applied",
      }),
    ).not.toBeInTheDocument();
  });

  it("does not misattribute terrain observations when counts differ", () => {
    renderResult({
      ...baseResult,
      terrain_status: {
        terrain_applied: false,
        fallback_reasons: ["safety_fallback"],
        route_acquisition_statuses: ["partial"],
        route_coverage_fractions: ["0.75"],
      },
    });

    expect(
      screen.getByText(/could not be aligned with the evaluated routes/),
    ).toBeInTheDocument();

    expect(screen.queryByText(/Usable coverage: 75%/)).not.toBeInTheDocument();
  });

  it("preserves electric energy consumption alongside terrain status", () => {
    renderResult({
      ...baseResult,
      route_evaluations: baseResult.route_evaluations.map((evaluation) => ({
        ...evaluation,
        energy_estimate: {
          cost: "3.50",
          consumption: {
            energy_type: "electricity",
            kilowatt_hours: "7.00",
          },
        },
      })),
      terrain_status: {
        terrain_applied: false,
        fallback_reasons: ["acquisition_disabled"],
        route_acquisition_statuses: ["unavailable", "unavailable"],
        route_coverage_fractions: [null, null],
      },
    });

    expect(screen.getAllByText("Energy used: 7.00 kWh")).toHaveLength(2);

    expect(
      screen.getByRole("heading", {
        name: "Baseline energy estimates used",
      }),
    ).toBeInTheDocument();
  });
});
