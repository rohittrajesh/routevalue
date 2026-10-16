import { describe, expect, it } from "vitest";

import {
  formatVehicleConfiguration,
  formatVehicleEfficiency,
} from "./vehicleDisplay";

describe("vehicle display formatting", () => {
  it("preserves gasoline MPG and fuel grade", () => {
    expect(
      formatVehicleEfficiency({
        powertrain: "gasoline",
        combined_mpg: "26",
        city_mpg: "23",
        highway_mpg: "31",
        fuel_grade: "premium",
      }),
    ).toBe("26 MPG combined · premium gasoline");
  });

  it("rounds BEV consumption only for display", () => {
    const specification = {
      powertrain: "bev" as const,
      combined_kwh_per_mile: "0.286981",
      city_kwh_per_mile: "0.25",
      highway_kwh_per_mile: "0.31",
    };

    expect(formatVehicleEfficiency(specification)).toBe(
      "28.7 kWh/100 miles combined · battery electric",
    );

    expect(specification.combined_kwh_per_mile).toBe("0.286981");
  });

  it("rejects nonfinite display values", () => {
    expect(
      formatVehicleEfficiency({
        powertrain: "bev",
        combined_kwh_per_mile: "NaN",
        city_kwh_per_mile: null,
        highway_kwh_per_mile: null,
      }),
    ).toBe("Electric efficiency unavailable");
  });

  it("expands single-speed automatic labels", () => {
    expect(formatVehicleConfiguration("Auto (A1)")).toBe(
      "Single-speed automatic",
    );
  });

  it("expands eight-speed automatic labels", () => {
    expect(formatVehicleConfiguration("Auto (S8), 4 cyl, 2.5 L")).toBe(
      "8-speed automatic, 4 cyl, 2.5 L",
    );
  });

  it("expands the Audi transmission and engine description", () => {
    expect(
      formatVehicleConfiguration("Auto (AM-S7), 4 cyl, 2.0 L, Turbo"),
    ).toBe("7-speed automated manual, 2.0L turbocharged 4-cylinder");
  });

  it("preserves unknown provider transmission codes", () => {
    expect(formatVehicleConfiguration("Auto (XYZ), 6 cyl, 3.0 L")).toBe(
      "Auto (XYZ), 6 cyl, 3.0 L",
    );
  });
});
