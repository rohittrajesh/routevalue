import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const { submitRequest } = vi.hoisted(() => ({
  submitRequest: {
    origin: {
      display_name: "Origin",
      latitude: 32.88,
      longitude: -117.23,
      source: "google_places",
      source_id: "origin-place-id",
    },
    destination: {
      display_name: "Destination",
      latitude: 32.73,
      longitude: -117.19,
      source: "google_places",
      source_id: "destination-place-id",
    },
    value_of_time_per_hour: "20.00",
    gasoline: {
      fuel_efficiency_mpg: "30",
      fuel_grade: "regular" as const,
      fuel_price_per_gallon: "4.50",
    },
  },
}));

vi.mock("./components/TripForm", () => ({
  default: ({
    onSubmit,
    isSubmitting,
  }: {
    onSubmit: (request: typeof submitRequest) => void;
    isSubmitting: boolean;
  }) => (
    <button
      type="button"
      disabled={isSubmitting}
      onClick={() => {
        onSubmit(submitRequest);
      }}
    >
      {isSubmitting ? "Comparing routes..." : "Submit test trip"}
    </button>
  ),
}));

describe("App trip evaluation failures", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a temporary-unavailable message for a network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    render(<App />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("RouteValue is temporarily unavailable.");
    expect(alert).toHaveTextContent(
      "RouteValue could not reach the server. Check your connection and try again.",
    );

    expect(alert).not.toHaveTextContent("Failed to fetch");
  });

  it("shows a temporary-unavailable message for a routing outage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
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
      ),
    );

    render(<App />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("RouteValue is temporarily unavailable.");
    expect(alert).toHaveTextContent(
      "Routes are temporarily unavailable. Please try again.",
    );
  });

  it("shows an input-specific heading for validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
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
      ),
    );

    render(<App />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("Check your trip information.");
    expect(alert).toHaveTextContent(
      "Some trip information is invalid. Please check your inputs.",
    );
  });

  it("uses the general evaluation heading for a routing response failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "routing_response_invalid",
            detail:
              "The routing service returned an invalid response. Please try again.",
          }),
          {
            status: 502,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    render(<App />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("We couldn't evaluate this trip.");
    expect(alert).toHaveTextContent(
      "The routing service returned an invalid response. Please try again.",
    );
  });

  it("clears the error when the user retries successfully", async () => {
    const successfulResponse = {
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

    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(successfulResponse), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const submitButton = screen.getByRole("button", {
      name: /submit test trip/i,
    });

    fireEvent.click(submitButton);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "RouteValue is temporarily unavailable.",
    );

    await waitFor(() => {
      expect(submitButton).toBeEnabled();
    });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
