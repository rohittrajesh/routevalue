import type { components } from "../api/generated/schema";

type ApiSchemas = components["schemas"];

export type ApiErrorCode = ApiSchemas["ApiErrorCode"];

export type ApiErrorResponse = ApiSchemas["ApiErrorResponse"];

export type ResolvedLocationInput = ApiSchemas["ResolvedLocationInput"];

export type GasolineGrade = ApiSchemas["GasolineGradeInput"];

// V1 request contracts remain unchanged.

type GeneratedGasolineInputs = ApiSchemas["GasolineInputs"];

export type GasolineInputs = Omit<
  GeneratedGasolineInputs,
  "fuel_efficiency_mpg" | "fuel_price_per_gallon"
> & {
  fuel_efficiency_mpg: string;
  fuel_price_per_gallon: string;
};

type GeneratedTripEvaluationRequest = ApiSchemas["TripEvaluationRequest"];

export type TripEvaluationRequest = Omit<
  GeneratedTripEvaluationRequest,
  "value_of_time_per_hour" | "gasoline"
> & {
  value_of_time_per_hour: string;
  gasoline: GasolineInputs;
};

// V2 authenticated profile-driven evaluation request contracts.

type GeneratedV2GasolineInputs = ApiSchemas["V2GasolineInputs"];

export type V2GasolineInputs = Omit<
  GeneratedV2GasolineInputs,
  "fuel_price_per_gallon"
> & {
  fuel_price_per_gallon: string;
};

type GeneratedV2ElectricityInputs = ApiSchemas["V2ElectricityInputs"];

export type V2ElectricityInputs = Omit<
  GeneratedV2ElectricityInputs,
  "price_per_kilowatt_hour"
> & {
  price_per_kilowatt_hour: string;
};

type GeneratedV2TripEvaluationRequest = ApiSchemas["V2TripEvaluationRequest"];

type V2EnergyPriceInputs =
  | {
      gasoline: V2GasolineInputs;
      electricity?: never;
    }
  | {
      gasoline?: never;
      electricity: V2ElectricityInputs;
    };

export type V2TripEvaluationRequest = Omit<
  GeneratedV2TripEvaluationRequest,
  "gasoline" | "electricity"
> &
  V2EnergyPriceInputs;

// Shared route, decision, and V1 response contracts.

export type RouteResponse = ApiSchemas["RouteResponse"];

export type RoutePointResponse = ApiSchemas["RoutePointResponse"];

export type RouteGeometryResponse = ApiSchemas["RouteGeometryResponse"];

export type EnergyEstimateResponse = ApiSchemas["EnergyEstimateResponse"];

export type CostBreakdownResponse = ApiSchemas["CostBreakdownResponse"];

export type EligibilityResponse = ApiSchemas["EligibilityResponse"];

export type RouteEvaluationResponse = ApiSchemas["RouteEvaluationResponse"];

export type DecisionResponse = ApiSchemas["DecisionResponse"];

export type TripEvaluationResponse = ApiSchemas["TripEvaluationResponse"];

// V2-only typed physical-energy response contracts.

export type V2GasolineConsumptionResponse =
  ApiSchemas["V2GasolineConsumptionResponse"];

export type V2ElectricConsumptionResponse =
  ApiSchemas["V2ElectricConsumptionResponse"];

export type V2EnergyConsumptionResponse =
  V2GasolineConsumptionResponse | V2ElectricConsumptionResponse;

export type V2EnergyEstimateResponse = ApiSchemas["V2EnergyEstimateResponse"];

export type V2RouteEvaluationResponse = ApiSchemas["V2RouteEvaluationResponse"];

export type V2TripEvaluationResponse = ApiSchemas["V2TripEvaluationResponse"];
