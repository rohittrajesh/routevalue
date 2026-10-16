import type { SavedVehicle } from "../api/v2Resources";

type VehicleSpecification = SavedVehicle["specification"];

export function formatVehicleEfficiency(
  specification: VehicleSpecification,
): string {
  if (specification.powertrain === "gasoline") {
    return `${specification.combined_mpg} MPG combined · ${specification.fuel_grade} gasoline`;
  }

  const kwhPerMile = Number(specification.combined_kwh_per_mile);

  if (!Number.isFinite(kwhPerMile) || kwhPerMile <= 0) {
    return "Electric efficiency unavailable";
  }

  const kwhPer100Miles = (kwhPerMile * 100).toFixed(1);

  return `${kwhPer100Miles} kWh/100 miles combined · battery electric`;
}

export function formatVehicleConfiguration(configuration: string): string {
  let formatted = configuration;

  const transmission = /^Auto \((A1|S(\d+)|AM-S(\d+))\)(?:,\s*|$)/.exec(
    formatted,
  );

  if (transmission) {
    let description: string;

    if (transmission[1] === "A1") {
      description = "Single-speed automatic";
    } else if (transmission[2]) {
      description = `${transmission[2]}-speed automatic`;
    } else {
      description = `${transmission[3]}-speed automated manual`;
    }

    const remaining = formatted.slice(transmission[0].length);

    formatted = remaining ? `${description}, ${remaining}` : description;
  }

  return formatted.replace(
    /(\d+)\s+cyl,\s*(\d+(?:\.\d+)?)\s*L,\s*Turbo\b/gi,
    (_, cylinders: string, liters: string) =>
      `${liters}L turbocharged ${cylinders}-cylinder`,
  );
}
