import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "../api/tripEvaluations";
import type { SavedVehicle, UserPreferences } from "../api/v2Resources";
import type { ResolvedLocationInput } from "../types/api";
import V2TripPlanner from "./V2TripPlanner";

const { evaluateMock } = vi.hoisted(() => ({ evaluateMock: vi.fn() }));

vi.mock("../api/v2Resources", () => ({ evaluateV2Trip: evaluateMock }));

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

vi.mock("./PlaceAutocompleteInput", () => ({
  default: ({
    label,
    onLocationChange,
  }: {
    label: string;
    onLocationChange: (value: ResolvedLocationInput | null) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onLocationChange(label === "Origin" ? origin : destination)
      }
    >
      Choose {label}
    </button>
  ),
}));

const base = {
  id: "11111111-1111-4111-8111-111111111111",
  year: 2023,
  make: "Toyota",
  model: "Camry",
  configuration: "Auto (S8)",
  source: "fueleconomy_gov",
  source_id: "123",
  saved_at: "2026-10-15T00:00:00Z",
  specification_retrieved_at: "2026-10-15T00:00:00Z",
};

const gasolineVehicle: SavedVehicle = {
  ...base,
  specification: {
    powertrain: "gasoline",
    fuel_grade: "regular",
    combined_mpg: "28",
    city_mpg: "24",
    highway_mpg: "31",
  },
};

const electricVehicle: SavedVehicle = {
  ...base,
  id: "22222222-2222-4222-8222-222222222222",
  make: "Tesla",
  model: "Model Y",
  specification: {
    powertrain: "bev",
    combined_kwh_per_mile: "0.28",
    city_kwh_per_mile: "0.26",
    highway_kwh_per_mile: "0.30",
  },
};

const preferences: UserPreferences = {
  value_of_time_per_hour: "20.50",
  default_vehicle_id: gasolineVehicle.id,
};

beforeEach(() => {
  vi.clearAllMocks();
  evaluateMock.mockResolvedValue({
    decision: {
      recommended_route: null,
      reason: null,
      numerical_tie: false,
      missing_data_present: false,
      candidate_count: 0,
      eligible_count: 0,
    },
    route_evaluations: [],
  });
});

async function selectLocations(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Choose Origin" }));
  await user.click(screen.getByRole("button", { name: "Choose Destination" }));
}

describe("V2TripPlanner", () => {
  it("discards an in-flight response when saved personalization changes", async () => {
    let complete!: (value: unknown) => void;
    evaluateMock.mockReturnValueOnce(
      new Promise((resolve) => {
        complete = resolve;
      }),
    );
    const user = userEvent.setup();
    const { rerender } = render(
      <V2TripPlanner vehicles={[gasolineVehicle]} preferences={preferences} />,
    );
    await selectLocations(user);
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    rerender(
      <V2TripPlanner
        vehicles={[gasolineVehicle]}
        preferences={{ ...preferences, value_of_time_per_hour: "35" }}
      />,
    );
    await act(async () =>
      complete({
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
    );
    expect(
      screen.queryByRole("heading", { name: "Your route comparison" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Compare routes" }),
    ).toBeEnabled();
  });
  it("requires saved personalization and both locations", async () => {
    const user = userEvent.setup();
    render(
      <V2TripPlanner
        vehicles={[]}
        preferences={{ value_of_time_per_hour: null, default_vehicle_id: null }}
      />,
    );
    await selectLocations(user);
    expect(
      screen.getByRole("button", { name: "Compare routes" }),
    ).toBeDisabled();
    expect(evaluateMock).not.toHaveBeenCalled();
  });

  it("selects the default vehicle and posts automatic gasoline request", async () => {
    const user = userEvent.setup();
    render(
      <V2TripPlanner
        vehicles={[gasolineVehicle, electricVehicle]}
        preferences={preferences}
      />,
    );
    expect(
      screen.getByRole("combobox", { name: "Vehicle for this trip" }),
    ).toHaveValue(gasolineVehicle.id);
    await selectLocations(user);
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    await waitFor(() => {
      expect(evaluateMock).toHaveBeenCalledWith({
        origin,
        destination,
        saved_vehicle_id: gasolineVehicle.id,
      });
    });
  });

  it("sends manual gasoline price and preserves decimal precision", async () => {
    const user = userEvent.setup();
    render(
      <V2TripPlanner vehicles={[gasolineVehicle]} preferences={preferences} />,
    );
    await selectLocations(user);
    await user.click(screen.getByRole("radio", { name: "Enter my price" }));
    await user.type(
      screen.getByRole("textbox", { name: "Gasoline price ($/gallon)" }),
      "4.125",
    );
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    await waitFor(() => {
      expect(evaluateMock).toHaveBeenCalledWith({
        origin,
        destination,
        saved_vehicle_id: gasolineVehicle.id,
        gasoline: { fuel_price_per_gallon: "4.125" },
      });
    });
  });

  it("requires electricity pricing when BEV is selected", async () => {
    const user = userEvent.setup();
    render(
      <V2TripPlanner
        vehicles={[gasolineVehicle, electricVehicle]}
        preferences={preferences}
      />,
    );
    await selectLocations(user);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Vehicle for this trip" }),
      electricVehicle.id,
    );
    expect(
      screen.queryByText("Automatic regional pricing (when available)"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Compare routes" }),
    ).toBeDisabled();
    await user.type(
      screen.getByRole("textbox", { name: /Electricity price/ }),
      "0.275",
    );
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    await waitFor(() => {
      expect(evaluateMock).toHaveBeenCalledWith({
        origin,
        destination,
        saved_vehicle_id: electricVehicle.id,
        electricity: { price_per_kilowatt_hour: "0.275" },
      });
    });
  });

  it("offers manual pricing after missing automatic gasoline price", async () => {
    evaluateMock.mockRejectedValueOnce(
      new ApiRequestError(
        "No eligible automatic gasoline price.",
        409,
        "gasoline_price_unavailable",
      ),
    );
    const user = userEvent.setup();
    render(
      <V2TripPlanner vehicles={[gasolineVehicle]} preferences={preferences} />,
    );
    await selectLocations(user);
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    expect(
      await screen.findByRole("button", { name: "Use manual gasoline price" }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Use manual gasoline price" }),
    );
    expect(
      screen.getByRole("textbox", { name: "Gasoline price ($/gallon)" }),
    ).toBeInTheDocument();
    await user.type(
      screen.getByRole("textbox", { name: "Gasoline price ($/gallon)" }),
      "5.25",
    );
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    await waitFor(() => expect(evaluateMock).toHaveBeenCalledTimes(2));
    expect(evaluateMock).toHaveBeenLastCalledWith({
      origin,
      destination,
      saved_vehicle_id: gasolineVehicle.id,
      gasoline: { fuel_price_per_gallon: "5.25" },
    });
  });

  it("preserves origin and destination when preferences refresh", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <V2TripPlanner vehicles={[gasolineVehicle]} preferences={preferences} />,
    );
    await selectLocations(user);
    rerender(
      <V2TripPlanner
        vehicles={[gasolineVehicle, electricVehicle]}
        preferences={{ ...preferences, value_of_time_per_hour: "30.00" }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Compare routes" }));
    await waitFor(() => expect(evaluateMock).toHaveBeenCalledTimes(1));
  });
});
