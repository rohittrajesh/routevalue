import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ResolvedLocationInput,
  TripEvaluationResponse,
} from "../types/api";

import TripResults from "./TripResults";

const googleMapsMocks = vi.hoisted(() => ({
  loadMapsLibrary: vi.fn(),
  loadCoreLibrary: vi.fn(),
}));

vi.mock("../integrations/googleMaps", () => googleMapsMocks);

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

const result: TripEvaluationResponse = {
  route_evaluations: [
    {
      route: {
        distance_meters: 10_000,
        duration_seconds: 900,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.00",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.00",
        time_cost: "4.50",
        generalized_cost: "6.50",
      },
      geometry: {
        points: [
          {
            latitude: 32.88,
            longitude: -117.23,
          },
          {
            latitude: 32.73,
            longitude: -117.19,
          },
        ],
      },
    },
  ],
  decision: {
    recommended_route: {
      distance_meters: 10_000,
      duration_seconds: 900,
      toll_cost: "0",
    },
    reason: "only_eligible_route",
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 1,
    eligible_count: 1,
  },
};

describe("TripResults map degradation", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    googleMapsMocks.loadMapsLibrary.mockRejectedValue(
      new Error("Maps unavailable"),
    );

    googleMapsMocks.loadCoreLibrary.mockResolvedValue({
      LatLngBounds: class {},
    });
  });

  it("keeps the route comparison usable when the map fails", async () => {
    render(
      <TripResults result={result} origin={origin} destination={destination} />,
    );

    expect(
      screen.getByRole("article", {
        name: /route 1, recommended/i,
      }),
    ).toBeInTheDocument();

    expect(screen.getAllByText("$6.50").length).toBeGreaterThan(0);

    expect(screen.getByText(/route 1 is your best match/i)).toBeInTheDocument();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The route comparison is available, but the map could not be loaded.",
    );

    expect(
      screen.getByRole("article", {
        name: /route 1, recommended/i,
      }),
    ).toBeInTheDocument();
  });
});
