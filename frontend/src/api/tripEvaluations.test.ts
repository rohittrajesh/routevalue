import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type {
  TripEvaluationRequest,
  TripEvaluationResponse,
} from "../types/api";

import {
  ApiRequestError,
  evaluateTrip,
} from "./tripEvaluations";

const request: TripEvaluationRequest = {
  origin: "Origin",
  destination: "Destination",
  value_of_time_per_hour: "20.00",
  gasoline: {
    fuel_efficiency_mpg: "30",
    fuel_grade: "regular",
    fuel_price_per_gallon: "4.50",
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("evaluateTrip", () => {
  it("returns a successful trip evaluation", async () => {
    const responseBody: TripEvaluationResponse = {
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

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => responseBody,
    } as Response);

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      evaluateTrip(request),
    ).resolves.toEqual(responseBody);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trip-evaluations",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("surfaces a stable API error message", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        detail: "routing provider unavailable",
      }),
    } as Response);

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      evaluateTrip(request),
    ).rejects.toEqual(
      expect.objectContaining({
        message: "routing provider unavailable",
        status: 503,
      }),
    );
  });

  it("uses a friendly message for validation failures", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [],
      }),
    } as Response);

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      evaluateTrip(request),
    ).rejects.toEqual(
      new ApiRequestError(
        "Some trip information is invalid. Please check your inputs.",
        422,
      ),
    );
  });
});