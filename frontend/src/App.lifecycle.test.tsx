import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const submitRequest = {
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
};

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
      onClick={() => {
        onSubmit(submitRequest);
      }}
    >
      {isSubmitting ? "Comparing routes..." : "Submit test trip"}
    </button>
  ),
}));

vi.mock("./components/TripResults", () => ({
  default: () => <div data-testid="trip-results">Rendered trip results</div>,
}));

function successfulResponse() {
  return new Response(
    JSON.stringify({
      route_evaluations: [],
      decision: {
        recommended_route: null,
        reason: null,
        numerical_tie: false,
        missing_data_present: false,
        candidate_count: 0,
        eligible_count: 0,
      },
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App trip submission lifecycle", () => {
  it("ignores a rapid duplicate submission while a request is in flight", async () => {
    let resolveRequest!: (response: Response) => void;

    const pendingResponse = new Promise<Response>((resolve) => {
      resolveRequest = resolve;
    });

    const fetchMock = vi.fn().mockReturnValue(pendingResponse);

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const submitButton = screen.getByRole("button", {
      name: /submit test trip/i,
    });

    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveRequest(successfulResponse());

    await waitFor(() => {
      expect(screen.getByTestId("trip-results")).toBeInTheDocument();
    });
  });

  it("clears stale results as soon as a new evaluation begins", async () => {
    let resolveSecondRequest!: (response: Response) => void;

    const secondResponse = new Promise<Response>((resolve) => {
      resolveSecondRequest = resolve;
    });

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(successfulResponse())
      .mockReturnValueOnce(secondResponse);

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    expect(await screen.findByTestId("trip-results")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /submit test trip/i,
      }),
    );

    expect(screen.queryByTestId("trip-results")).not.toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: /comparing routes/i,
      }),
    ).toBeInTheDocument();

    resolveSecondRequest(successfulResponse());

    await waitFor(() => {
      expect(screen.getByTestId("trip-results")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
