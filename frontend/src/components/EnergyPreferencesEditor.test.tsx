import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { UserPreferences } from "../api/v2Resources";
import type { ResolvedLocationInput } from "../types/api";
import EnergyPreferencesEditor from "./EnergyPreferencesEditor";

vi.mock("./PlaceAutocompleteInput", () => ({
  default: ({
    onLocationChange,
  }: {
    onLocationChange: (value: ResolvedLocationInput | null) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onLocationChange({
          display_name: "Raleigh, NC",
          latitude: 35.7796,
          longitude: -78.6382,
          source: "google_places",
          source_id: "fixture-place",
        })
      }
    >
      Choose purchasing area
    </button>
  ),
}));

const preferences: UserPreferences = {
  value_of_time_per_hour: "24",
  default_vehicle_id: null,
  electricity_price_per_kwh: "0.275",
  preferred_fuel_market: {
    display_name: "Raleigh, NC",
    latitude: 35.7796,
    longitude: -78.6382,
  },
};

describe("EnergyPreferencesEditor", () => {
  it("loads the saved rate, saves zero precisely and clears only that preference", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(true);
    render(
      <EnergyPreferencesEditor
        preferences={preferences}
        busy={false}
        onSave={onSave}
      />,
    );
    const input = screen.getByLabelText("Saved electricity rate ($/kWh)");
    expect(input).toHaveValue("0.275");
    await user.clear(input);
    await user.type(input, "0");
    await user.click(
      screen.getByRole("button", { name: "Save electricity rate" }),
    );
    expect(onSave).toHaveBeenLastCalledWith(
      { electricity_price_per_kwh: "0" },
      "Electricity rate saved.",
    );
    await user.clear(input);
    await user.click(
      screen.getByRole("button", { name: "Save electricity rate" }),
    );
    expect(onSave).toHaveBeenLastCalledWith(
      { electricity_price_per_kwh: null },
      "Electricity rate cleared.",
    );
  });

  it.each(["-1", "NaN", "Infinity", "1e5"])(
    "rejects invalid rate %s without saving",
    async (value) => {
      const user = userEvent.setup();
      const onSave = vi.fn().mockResolvedValue(true);
      render(
        <EnergyPreferencesEditor
          preferences={preferences}
          busy={false}
          onSave={onSave}
        />,
      );
      const input = screen.getByLabelText("Saved electricity rate ($/kWh)");
      await user.clear(input);
      await user.type(input, value);
      await user.click(
        screen.getByRole("button", { name: "Save electricity rate" }),
      );
      expect(screen.getByRole("alert")).toHaveTextContent(
        "non-negative electricity rate",
      );
      expect(
        within(
          screen.getByRole("region", { name: "Energy preferences" }),
        ).getByRole("alert"),
      ).toHaveTextContent("non-negative electricity rate");
      expect(
        within(
          screen.getByRole("region", {
            name: "Preferred fuel market",
          }),
        ).queryByRole("alert"),
      ).not.toBeInTheDocument();
      expect(onSave).not.toHaveBeenCalled();
    },
  );

  it("requires a resolved market and excludes provider identifiers from saved user settings", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(true);
    render(
      <EnergyPreferencesEditor
        preferences={preferences}
        busy={false}
        onSave={onSave}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Save fuel market" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Choose purchasing area" }),
    );
    await user.click(screen.getByRole("button", { name: "Save fuel market" }));
    expect(onSave).toHaveBeenLastCalledWith(
      { preferred_fuel_market: preferences.preferred_fuel_market },
      "Fuel market saved.",
    );
    await user.click(screen.getByRole("button", { name: "Clear fuel market" }));
    expect(onSave).toHaveBeenLastCalledWith(
      { preferred_fuel_market: null },
      "Fuel market cleared. Automatic pricing will use the trip origin.",
    );
  });

  it("does not invent defaults and disables writes during an account mutation", () => {
    const onSave = vi.fn();
    render(
      <EnergyPreferencesEditor
        preferences={{ value_of_time_per_hour: null, default_vehicle_id: null }}
        busy={true}
        onSave={onSave}
      />,
    );
    expect(screen.getByLabelText("Saved electricity rate ($/kWh)")).toHaveValue(
      "",
    );
    expect(screen.getByText("No electricity rate saved.")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Save electricity rate" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Clear fuel market" }),
    ).toBeDisabled();
  });
});
