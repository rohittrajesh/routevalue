import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "../api/tripEvaluations";
import PersonalizationDashboard from "./PersonalizationDashboard";

const { vehiclesMock, preferencesMock, updateMock, createMock, deleteMock } =
  vi.hoisted(() => ({
    vehiclesMock: vi.fn(),
    preferencesMock: vi.fn(),
    updateMock: vi.fn(),
    createMock: vi.fn(),
    deleteMock: vi.fn(),
  }));

vi.mock("../api/v2Resources", () => ({
  getSavedVehicles: vehiclesMock,
  getUserPreferences: preferencesMock,
  updateUserPreferences: updateMock,
  createSavedVehicle: createMock,
  deleteSavedVehicle: deleteMock,
}));

vi.mock("./VehicleCatalogPicker", () => ({
  default: ({
    onSave,
  }: {
    onSave: (configuration: {
      year: number;
      make: string;
      model: string;
      configuration: string;
      source: string;
      source_id: string;
    }) => Promise<boolean>;
  }) => (
    <button
      type="button"
      onClick={() =>
        void onSave({
          year: 2025,
          make: "Toyota",
          model: "Camry",
          configuration: "2.5L FWD",
          source: "fueleconomy_gov",
          source_id: "12345",
        })
      }
    >
      Save example vehicle
    </button>
  ),
}));

const gasolineVehicle = {
  id: "11111111-1111-4111-8111-111111111111",
  year: 2025,
  make: "Toyota",
  model: "Camry",
  configuration: "Auto (S8), 4 cyl, 2.5 L",
  source: "fueleconomy_gov",
  source_id: "12345",
  saved_at: "2026-10-15T00:00:00Z",
  specification_retrieved_at: "2026-10-15T00:00:00Z",
  specification: {
    powertrain: "gasoline",
    combined_mpg: "32.5",
    city_mpg: "29",
    highway_mpg: "38",
    fuel_grade: "regular",
  },
};

const electricVehicle = {
  ...gasolineVehicle,
  id: "22222222-2222-4222-8222-222222222222",
  make: "Tesla",
  model: "Model 3",
  configuration: "Auto (A1)",
  specification: {
    powertrain: "bev",
    combined_kwh_per_mile: "0.286981",
    city_kwh_per_mile: "0.22",
    highway_kwh_per_mile: "0.31",
  },
};

beforeEach(() => {
  vi.clearAllMocks();

  vehiclesMock.mockResolvedValue({
    vehicles: [],
  });

  preferencesMock.mockResolvedValue({
    value_of_time_per_hour: null,
    default_vehicle_id: null,
  });

  updateMock.mockResolvedValue({
    value_of_time_per_hour: null,
    default_vehicle_id: null,
  });

  createMock.mockResolvedValue(gasolineVehicle);
  deleteMock.mockResolvedValue(undefined);
});

describe("PersonalizationDashboard", () => {
  it("loads an empty account", async () => {
    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    expect(
      await screen.findByText(
        "No vehicles saved yet. Add your first vehicle below.",
      ),
    ).toBeInTheDocument();

    expect(vehiclesMock).toHaveBeenCalled();
    expect(preferencesMock).toHaveBeenCalled();
  });

  it("displays readable gasoline and BEV specifications", async () => {
    vehiclesMock.mockResolvedValue({
      vehicles: [gasolineVehicle, electricVehicle],
    });

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    expect(
      await screen.findByText("32.5 MPG combined · regular gasoline"),
    ).toBeInTheDocument();

    expect(
      screen.getByText("28.7 kWh/100 miles combined · battery electric"),
    ).toBeInTheDocument();

    expect(screen.getByText("Single-speed automatic")).toBeInTheDocument();

    expect(
      screen.getByText("8-speed automatic, 4 cyl, 2.5 L"),
    ).toBeInTheDocument();
  });

  it("saves value of time as a decimal string", async () => {
    const user = userEvent.setup();
    const onProfileChanged = vi.fn();

    render(<PersonalizationDashboard onProfileChanged={onProfileChanged} />);

    const input = await screen.findByLabelText("Value of time ($/hour)");

    await user.type(input, "37.125");

    await user.click(
      screen.getByRole("button", {
        name: "Save preferences",
      }),
    );

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith({
        value_of_time_per_hour: "37.125",
      });
    });

    expect(onProfileChanged).toHaveBeenCalled();
  });

  it("rejects invalid value of time before an API call", async () => {
    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    const input = await screen.findByLabelText("Value of time ($/hour)");

    await user.type(input, "-1");

    await user.click(
      screen.getByRole("button", {
        name: "Save preferences",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "non-negative decimal",
    );

    expect(updateMock).not.toHaveBeenCalled();
  });

  it("sets a saved vehicle as default", async () => {
    vehiclesMock.mockResolvedValue({
      vehicles: [gasolineVehicle],
    });

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByText("2025 Toyota Camry");

    await user.click(
      screen.getByRole("button", {
        name: "Set as default",
      }),
    );

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith({
        default_vehicle_id: gasolineVehicle.id,
      });
    });
  });

  it("clears the default vehicle", async () => {
    vehiclesMock.mockResolvedValue({
      vehicles: [gasolineVehicle],
    });

    preferencesMock.mockResolvedValue({
      value_of_time_per_hour: "25.00",
      default_vehicle_id: gasolineVehicle.id,
    });

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByRole("button", {
      name: "Clear default vehicle",
    });

    await user.click(
      screen.getByRole("button", {
        name: "Clear default vehicle",
      }),
    );

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith({
        default_vehicle_id: null,
      });
    });
  });

  it("saves the exact provider catalog identity", async () => {
    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByText(
      "No vehicles saved yet. Add your first vehicle below.",
    );

    await user.click(
      screen.getByRole("button", {
        name: "Save example vehicle",
      }),
    );

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith({
        year: 2025,
        make: "Toyota",
        model: "Camry",
        configuration: "2.5L FWD",
        source: "fueleconomy_gov",
        source_id: "12345",
      });
    });
  });

  it("prevents an already loaded vehicle from being saved twice", async () => {
    vehiclesMock.mockResolvedValue({
      vehicles: [gasolineVehicle],
    });

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByText("2025 Toyota Camry");

    await user.click(
      screen.getByRole("button", {
        name: "Save example vehicle",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "already in your garage",
    );

    expect(createMock).not.toHaveBeenCalled();
  });

  it("explains an unsupported vehicle specification", async () => {
    createMock.mockRejectedValueOnce(
      new ApiRequestError(
        "The selected vehicle does not have a supported energy specification.",
        409,
        "vehicle_specification_unavailable",
      ),
    );

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByText(
      "No vehicles saved yet. Add your first vehicle below.",
    );

    await user.click(
      screen.getByRole("button", {
        name: "Save example vehicle",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "cannot currently model its energy use",
    );
  });

  it("requires confirmation before deletion", async () => {
    vehiclesMock.mockResolvedValue({
      vehicles: [gasolineVehicle],
    });

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    await screen.findByText("2025 Toyota Camry");

    await user.click(
      screen.getByRole("button", {
        name: "Delete 2025 Toyota Camry",
      }),
    );

    expect(deleteMock).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", {
        name: "Confirm delete",
      }),
    );

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith(gasolineVehicle.id);
    });
  });

  it("supports retrying initial loading failure", async () => {
    vehiclesMock
      .mockRejectedValueOnce(new Error("Temporary outage"))
      .mockResolvedValue({
        vehicles: [],
      });

    const user = userEvent.setup();

    render(<PersonalizationDashboard onProfileChanged={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load",
    );

    await user.click(
      screen.getByRole("button", {
        name: "Retry dashboard",
      }),
    );

    expect(
      await screen.findByText(
        "No vehicles saved yet. Add your first vehicle below.",
      ),
    ).toBeInTheDocument();
  });
});

it("keeps garage save feedback out of Settings while retaining its drafts", async () => {
  const user = userEvent.setup();
  const onProfileChanged = vi.fn();
  const { rerender } = render(
    <PersonalizationDashboard
      view="garage"
      onProfileChanged={onProfileChanged}
    />,
  );
  await screen.findByText(
    "No vehicles saved yet. Add your first vehicle below.",
  );
  await user.click(
    screen.getByRole("button", { name: "Save example vehicle" }),
  );
  expect(
    await screen.findByText("Vehicle saved to your account."),
  ).toBeVisible();
  rerender(
    <PersonalizationDashboard
      view="settings"
      onProfileChanged={onProfileChanged}
    />,
  );
  expect(
    screen.queryByText("Vehicle saved to your account."),
  ).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Value of time ($/hour)"), "32.75");
  rerender(
    <PersonalizationDashboard
      view="garage"
      onProfileChanged={onProfileChanged}
    />,
  );
  expect(screen.getByLabelText("Value of time ($/hour)")).not.toBeVisible();
  rerender(
    <PersonalizationDashboard
      view="settings"
      onProfileChanged={onProfileChanged}
    />,
  );
  expect(screen.getByLabelText("Value of time ($/hour)")).toHaveValue("32.75");
});
