import { describe, expect, it } from "vitest";

import type { SavedVehicle } from "../api/v2Resources";
import type { ResolvedLocationInput } from "../types/api";
import { buildV2TripRequest, isValidNonnegativeDecimal } from "./v2TripRequest";

const origin: ResolvedLocationInput = {
  display_name: "Origin",
  latitude: 32.88,
  longitude: -117.23,
  source: "google_places",
  source_id: "origin-id",
};

const destination: ResolvedLocationInput = {
  display_name: "Destination",
  latitude: 32.73,
  longitude: -117.19,
  source: "google_places",
  source_id: "destination-id",
};

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

const common = {
  origin,
  destination,
  gasolinePricingMode: "automatic" as const,
  gasolinePrice: "",
  electricityPrice: "",
};

describe("buildV2TripRequest", () => {
  it("omits energy-price objects for automatic gasoline pricing", () => {
    expect(buildV2TripRequest({ ...common, vehicle: gasolineVehicle })).toEqual(
      {
        origin,
        destination,
        saved_vehicle_id: gasolineVehicle.id,
      },
    );
  });

  it("sends a manual gasoline price as a decimal string", () => {
    expect(
      buildV2TripRequest({
        ...common,
        vehicle: gasolineVehicle,
        gasolinePricingMode: "manual",
        gasolinePrice: " 4.125 ",
      }),
    ).toEqual({
      origin,
      destination,
      saved_vehicle_id: gasolineVehicle.id,
      gasoline: { fuel_price_per_gallon: "4.125" },
    });
  });

  it("requires a BEV electricity price and never sends gasoline", () => {
    expect(
      buildV2TripRequest({
        ...common,
        vehicle: electricVehicle,
        electricityPrice: "0.275",
      }),
    ).toEqual({
      origin,
      destination,
      saved_vehicle_id: electricVehicle.id,
      electricity: { price_per_kilowatt_hour: "0.275" },
    });
  });

  it("rejects negative, nonfinite and missing prices", () => {
    for (const value of ["", "-1", "NaN", "Infinity", "1e10", "1.2.3"]) {
      expect(isValidNonnegativeDecimal(value)).toBe(false);
    }
    expect(isValidNonnegativeDecimal("0")).toBe(true);
    expect(isValidNonnegativeDecimal("0.125")).toBe(true);
    expect(() =>
      buildV2TripRequest({
        ...common,
        vehicle: gasolineVehicle,
        gasolinePricingMode: "manual",
        gasolinePrice: "-1",
      }),
    ).toThrow("gasoline price");
    expect(() =>
      buildV2TripRequest({ ...common, vehicle: electricVehicle }),
    ).toThrow("electricity price");
  });
});
