import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TripEvaluationResponse } from "../types/api";

import TripResults from "./TripResults";

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
    render(<TripResults result={successfulResult} />);

    expect(screen.getAllByText("$9.85").length).toBeGreaterThan(0);

    expect(screen.getByText("$12.10")).toBeInTheDocument();

    expect(screen.getAllByText("Value of travel time")).toHaveLength(2);
  });

  it("marks the backend-recommended route as the best match", () => {
    render(<TripResults result={successfulResult} />);

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

    render(<TripResults result={unavailableResult} />);

    expect(screen.getByText(/unable to score this route/i)).toBeInTheDocument();

    expect(
      screen.getByText(/toll information is unavailable/i),
    ).toBeInTheDocument();
  });
});
