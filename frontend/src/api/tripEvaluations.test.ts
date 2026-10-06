import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  TripEvaluationRequest,
  TripEvaluationResponse,
} from "../types/api";

import { ApiRequestError, evaluateTrip } from "./tripEvaluations";

const request: TripEvaluationRequest = {
  origin: {
    display_name: "Origin",
    latitude: 32.88,
    longitude: -117.23,
    source: "google_places",
    source_id: "origin-place-id",
  },
  destination: {
    display_name: "Destination",
    latitude: 32.88,
    longitude: -117.23,
    source: "google_places",
    source_id: "destination-place-id",
  },
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

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).resolves.toEqual(responseBody);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trip-evaluations",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("preserves a structured RouteValue API failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "routing_service_unavailable",
          detail: "Routes are temporarily unavailable. Please try again.",
        }),
        {
          status: 503,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "Routes are temporarily unavailable. Please try again.",
        503,
        "routing_service_unavailable",
      ),
    );
  });

  it("uses a friendly validation failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [],
        }),
        {
          status: 422,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "Some trip information is invalid. Please check your inputs.",
        422,
        "validation_error",
      ),
    );
  });

  it("normalizes a browser network failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError("Failed to fetch"));

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "RouteValue could not reach the server. Check your connection and try again.",
        null,
        "network_error",
      ),
    );
  });

  it("uses a safe fallback for an unstructured HTTP failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          unexpected: "server details",
        }),
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "RouteValue could not evaluate this trip. Please try again.",
        500,
        "unknown_error",
      ),
    );
  });

  it("uses a safe fallback when an error response is not JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("not-json", {
        status: 502,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "RouteValue could not evaluate this trip. Please try again.",
        502,
        "unknown_error",
      ),
    );
  });

  it("normalizes an invalid successful response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("not-json", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(evaluateTrip(request)).rejects.toEqual(
      new ApiRequestError(
        "RouteValue received an unexpected response. Please try again.",
        200,
        "unexpected_response",
      ),
    );
  });
});
