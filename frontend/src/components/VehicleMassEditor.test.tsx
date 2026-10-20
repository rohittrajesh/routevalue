import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SavedVehicle } from "../api/v2Resources";
import VehicleMassEditor from "./VehicleMassEditor";

const { updateMassMock } = vi.hoisted(() => ({
  updateMassMock: vi.fn(),
}));

vi.mock("../api/v2Resources", () => ({
  updateSavedVehicleMass: updateMassMock,
}));

const vehicle: SavedVehicle = {
  id: "11111111-1111-4111-8111-111111111111",
  year: 2023,
  make: "Toyota",
  model: "Camry",
  configuration: "2.5L AWD",
  source: "fueleconomy_gov",
  source_id: "12345",
  specification_retrieved_at: "2026-10-16T00:00:00Z",
  saved_at: "2026-10-16T00:00:00Z",
  specification: {
    powertrain: "gasoline",
    fuel_grade: "regular",
    combined_mpg: "28",
    city_mpg: "25",
    highway_mpg: "30",
  },
  vehicle_mass: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  updateMassMock.mockResolvedValue(vehicle);
});

describe("VehicleMassEditor", () => {
  it("shows unconfigured mass without guessing a weight", () => {
    render(
      <VehicleMassEditor
        vehicle={vehicle}
        disabled={false}
        onUpdated={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Vehicle mass not configured."),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Add vehicle weight" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Curb weight is optional and entered by you/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /lookup|automatic|resolve/i }),
    ).not.toBeInTheDocument();
    expect(updateMassMock).not.toHaveBeenCalled();
  });

  it("saves weight and source without floating-point conversion", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn().mockResolvedValue(undefined);

    render(
      <VehicleMassEditor
        vehicle={vehicle}
        disabled={false}
        onUpdated={onUpdated}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Add vehicle weight" }),
    );

    await user.type(screen.getByLabelText("Curb weight"), "3900.125");
    await user.type(
      screen.getByLabelText("Weight source"),
      "Published vehicle specification",
    );

    await user.click(
      screen.getByRole("button", { name: "Save vehicle weight" }),
    );

    await waitFor(() => {
      expect(updateMassMock).toHaveBeenCalledWith(vehicle.id, {
        weight: "3900.125",
        unit: "lb",
        source_reference: "Published vehicle specification",
      });
    });

    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
  });

  it("requires a source note", async () => {
    const user = userEvent.setup();

    render(
      <VehicleMassEditor
        vehicle={vehicle}
        disabled={false}
        onUpdated={vi.fn()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Add vehicle weight" }),
    );

    await user.type(screen.getByLabelText("Curb weight"), "3900");

    await user.click(
      screen.getByRole("button", { name: "Save vehicle weight" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "where you found",
    );
    expect(updateMassMock).not.toHaveBeenCalled();
  });

  it("requires confirmation before clearing stored mass", async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn().mockResolvedValue(undefined);

    const withMass: SavedVehicle = {
      ...vehicle,
      vehicle_mass: {
        kilograms: "1800",
        source: "user_provided",
        source_reference: "Owner's manual",
      },
    };

    render(
      <VehicleMassEditor
        vehicle={withMass}
        disabled={false}
        onUpdated={onUpdated}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Clear vehicle weight" }),
    );

    expect(updateMassMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirm clear" }));

    await waitFor(() => {
      expect(updateMassMock).toHaveBeenCalledWith(vehicle.id, {
        weight: null,
      });
    });

    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
  });

  it("updates an existing weight in kilograms with user provenance", async () => {
    const user = userEvent.setup();
    render(
      <VehicleMassEditor
        vehicle={{
          ...vehicle,
          vehicle_mass: {
            kilograms: "1800",
            source: "user_provided",
            source_reference: "Original note",
          },
        }}
        disabled={false}
        onUpdated={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(
      screen.getByText(/User-provided curb weight · Original note/),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Update vehicle weight" }),
    );
    await user.type(screen.getByLabelText("Curb weight"), "1950.125");
    await user.selectOptions(screen.getByLabelText("Unit"), "kg");
    await user.type(
      screen.getByLabelText("Weight source"),
      "Updated owner entry",
    );
    await user.click(
      screen.getByRole("button", { name: "Save vehicle weight" }),
    );
    await waitFor(() =>
      expect(updateMassMock).toHaveBeenCalledWith(vehicle.id, {
        weight: "1950.125",
        unit: "kg",
        source_reference: "Updated owner entry",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Vehicle mass saved.",
    );
  });
});
