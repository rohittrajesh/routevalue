import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VehicleCatalogPicker from "./VehicleCatalogPicker";

const { yearsMock, makesMock, modelsMock, configurationsMock } = vi.hoisted(
  () => ({
    yearsMock: vi.fn(),
    makesMock: vi.fn(),
    modelsMock: vi.fn(),
    configurationsMock: vi.fn(),
  }),
);

vi.mock("../api/vehicleCatalog", () => ({
  getVehicleYears: yearsMock,
  getVehicleMakes: makesMock,
  getVehicleModels: modelsMock,
  getVehicleConfigurations: configurationsMock,
}));

const configuration = {
  year: 2025,
  make: "Toyota",
  model: "Camry",
  configuration: "2.5L FWD",
  source: "fueleconomy_gov",
  source_id: "12345",
};

beforeEach(() => {
  vi.clearAllMocks();

  yearsMock.mockResolvedValue([2025, 2024]);
  makesMock.mockResolvedValue(["Toyota"]);
  modelsMock.mockResolvedValue(["Camry"]);
  configurationsMock.mockResolvedValue([configuration]);
});

async function selectVehicle(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(screen.getByLabelText("Model year")).toBeEnabled();
  });

  await user.selectOptions(screen.getByLabelText("Model year"), "2025");

  await waitFor(() => {
    expect(screen.getByLabelText("Make")).toBeEnabled();
  });

  await user.selectOptions(screen.getByLabelText("Make"), "Toyota");

  await waitFor(() => {
    expect(screen.getByLabelText("Model")).toBeEnabled();
  });

  await user.selectOptions(screen.getByLabelText("Model"), "Camry");

  await waitFor(() => {
    expect(screen.getByLabelText("Configuration")).toBeEnabled();
  });

  await user.selectOptions(screen.getByLabelText("Configuration"), "12345");
}

describe("VehicleCatalogPicker", () => {
  it("loads available model years", async () => {
    render(<VehicleCatalogPicker onSave={vi.fn()} />);

    await waitFor(() => {
      expect(yearsMock).toHaveBeenCalledTimes(1);
    });

    expect(
      await screen.findByRole("option", { name: "2025" }),
    ).toBeInTheDocument();
  });

  it("loads selections in hierarchical order", async () => {
    const user = userEvent.setup();
    render(<VehicleCatalogPicker onSave={vi.fn()} />);

    await selectVehicle(user);

    expect(makesMock).toHaveBeenCalledWith(2025);
    expect(modelsMock).toHaveBeenCalledWith(2025, "Toyota");
    expect(configurationsMock).toHaveBeenCalledWith(2025, "Toyota", "Camry");
  });

  it("submits the exact selected catalog identity", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(true);

    render(<VehicleCatalogPicker onSave={onSave} />);

    await selectVehicle(user);

    await user.click(screen.getByRole("button", { name: "Save vehicle" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(configuration);
    });
  });

  it("clears dependent selections when the year changes", async () => {
    const user = userEvent.setup();

    render(<VehicleCatalogPicker onSave={vi.fn()} />);

    await selectVehicle(user);

    await user.selectOptions(screen.getByLabelText("Model year"), "2024");

    expect(screen.getByLabelText("Model")).toHaveValue("");
    expect(screen.getByLabelText("Configuration")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Save vehicle" })).toBeDisabled();
  });

  it("provides retry recovery for catalog failures", async () => {
    yearsMock
      .mockRejectedValueOnce(new Error("Temporary outage"))
      .mockResolvedValue([2025]);

    const user = userEvent.setup();

    render(<VehicleCatalogPicker onSave={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load vehicle options",
    );

    await user.click(screen.getByRole("button", { name: "Retry catalog" }));

    expect(
      await screen.findByRole("option", { name: "2025" }),
    ).toBeInTheDocument();
  });

  it("does not clear the selection after a failed save", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(false);

    render(<VehicleCatalogPicker onSave={onSave} />);

    await selectVehicle(user);

    await user.click(screen.getByRole("button", { name: "Save vehicle" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByLabelText("Configuration")).toHaveValue("12345");
  });
});
