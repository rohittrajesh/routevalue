import type { SavedVehicle } from "../api/v2Resources";
import type {
  ResolvedLocationInput,
  V2TripEvaluationRequest,
} from "../types/api";

export type GasolinePricingMode = "automatic" | "manual";

export interface V2TripInputs {
  origin: ResolvedLocationInput;
  destination: ResolvedLocationInput;
  vehicle: SavedVehicle;
  gasolinePricingMode: GasolinePricingMode;
  gasolinePrice: string;
  electricityPrice: string;
}

export function isValidNonnegativeDecimal(value: string): boolean {
  return /^\d+(?:\.\d+)?$/.test(value.trim());
}

export function buildV2TripRequest(
  inputs: V2TripInputs,
): V2TripEvaluationRequest {
  const base = {
    origin: inputs.origin,
    destination: inputs.destination,
    saved_vehicle_id: inputs.vehicle.id,
  };

  if (inputs.vehicle.specification.powertrain === "bev") {
    const price = inputs.electricityPrice.trim();
    if (!isValidNonnegativeDecimal(price)) {
      throw new Error("Enter a valid non-negative electricity price per kWh.");
    }
    return {
      ...base,
      electricity: { price_per_kilowatt_hour: price },
    };
  }

  if (inputs.gasolinePricingMode === "manual") {
    const price = inputs.gasolinePrice.trim();
    if (!isValidNonnegativeDecimal(price)) {
      throw new Error("Enter a valid non-negative gasoline price per gallon.");
    }
    return {
      ...base,
      gasoline: { fuel_price_per_gallon: price },
    };
  }

  return base;
}
