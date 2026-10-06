import type { components } from "../api/generated/schema";

type ApiSchemas = components["schemas"];

export type ApiErrorCode = ApiSchemas["ApiErrorCode"];

export type ApiErrorResponse = ApiSchemas["ApiErrorResponse"];

export type ResolvedLocationInput = ApiSchemas["ResolvedLocationInput"];

export type GasolineGrade = ApiSchemas["GasolineGradeInput"];

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

export type RouteResponse = ApiSchemas["RouteResponse"];

export type RoutePointResponse = ApiSchemas["RoutePointResponse"];

export type RouteGeometryResponse = ApiSchemas["RouteGeometryResponse"];

export type EnergyEstimateResponse = ApiSchemas["EnergyEstimateResponse"];

export type CostBreakdownResponse = ApiSchemas["CostBreakdownResponse"];

export type EligibilityResponse = ApiSchemas["EligibilityResponse"];

export type RouteEvaluationResponse = ApiSchemas["RouteEvaluationResponse"];

export type DecisionResponse = ApiSchemas["DecisionResponse"];

export type TripEvaluationResponse = ApiSchemas["TripEvaluationResponse"];
