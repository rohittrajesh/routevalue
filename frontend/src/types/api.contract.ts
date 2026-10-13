/**
 * Compile-time assertions for RouteValue V1/V2 evaluation contracts.
 *
 * Checked by TypeScript during `npm run build`.
 * No runtime code or network calls are generated.
 */

import type { paths } from "../api/generated/schema";

import type {
  EnergyEstimateResponse,
  GasolineInputs,
  TripEvaluationRequest,
  TripEvaluationResponse,
  V2ElectricConsumptionResponse,
  V2ElectricityInputs,
  V2EnergyEstimateResponse,
  V2GasolineConsumptionResponse,
  V2GasolineInputs,
  V2TripEvaluationRequest,
  V2TripEvaluationResponse,
} from "./api";

type Assert<Condition extends true> = Condition;

type Assignable<Source, Destination> = [Source] extends [Destination]
  ? true
  : false;

type V1Operation = paths["/trip-evaluations"]["post"];

type V2Operation = paths["/api/v2/trip-evaluations"]["post"];

type V1RequestBody = V1Operation["requestBody"]["content"]["application/json"];

type V2RequestBody = V2Operation["requestBody"]["content"]["application/json"];

type V1Success = V1Operation["responses"][200]["content"]["application/json"];

type V2Success = V2Operation["responses"][200]["content"]["application/json"];

// Generated frontend types must remain compatible with HTTP contracts.

export type CheckV1RequestCompatible = Assert<
  Assignable<TripEvaluationRequest, V1RequestBody>
>;

export type CheckV2RequestCompatible = Assert<
  Assignable<V2TripEvaluationRequest, V2RequestBody>
>;

export type CheckV1ResponseCompatible = Assert<
  Assignable<V1Success, TripEvaluationResponse>
>;

export type CheckV2ResponseCompatible = Assert<
  Assignable<V2Success, V2TripEvaluationResponse>
>;

// V1 must retain its original request and cost-only response.

export type CheckV1StillHasEfficiency = Assert<
  "fuel_efficiency_mpg" extends keyof GasolineInputs ? true : false
>;

export type CheckV1StillHasValueOfTime = Assert<
  "value_of_time_per_hour" extends keyof TripEvaluationRequest ? true : false
>;

export type CheckV1HasNoPhysicalConsumption = Assert<
  "consumption" extends keyof EnergyEstimateResponse ? false : true
>;

// V2 must use persisted personalization and stored vehicle efficiency.

export type CheckV2HasNoClientValueOfTime = Assert<
  "value_of_time_per_hour" extends keyof V2TripEvaluationRequest ? false : true
>;

export type CheckV2HasNoClientUserId = Assert<
  "user_id" extends keyof V2TripEvaluationRequest ? false : true
>;

export type CheckV2HasNoClientEfficiency = Assert<
  "fuel_efficiency_mpg" extends keyof V2GasolineInputs ? false : true
>;

export type CheckV2HasNoClientFuelGrade = Assert<
  "fuel_grade" extends keyof V2GasolineInputs ? false : true
>;

export type CheckV2HasNoClientElectricEfficiency = Assert<
  "combined_kwh_per_mile" extends keyof V2ElectricityInputs ? false : true
>;

// Exact decimal price strings must be accepted by the generated schema.

export type CheckV2GasPriceIsDecimalString = Assert<
  Assignable<V2GasolineInputs["fuel_price_per_gallon"], string>
>;

export type CheckV2ElectricPriceIsDecimalString = Assert<
  Assignable<V2ElectricityInputs["price_per_kilowatt_hour"], string>
>;

// Vehicle selection remains optional.

export type CheckV2HasOptionalVehicleSelection = Assert<
  Assignable<
    V2TripEvaluationRequest["saved_vehicle_id"],
    string | null | undefined
  >
>;

// Exactly one powertrain-specific pricing object is required.

type V2CommonRequest = Pick<V2TripEvaluationRequest, "origin" | "destination">;

type V2GasolineRequest = V2CommonRequest & {
  gasoline: V2GasolineInputs;
};

type V2ElectricityRequest = V2CommonRequest & {
  electricity: V2ElectricityInputs;
};

type V2BothPricesRequest = V2CommonRequest & {
  gasoline: V2GasolineInputs;
  electricity: V2ElectricityInputs;
};

export type CheckV2AllowsGasolineOnly = Assert<
  Assignable<V2GasolineRequest, V2TripEvaluationRequest>
>;

export type CheckV2AllowsElectricityOnly = Assert<
  Assignable<V2ElectricityRequest, V2TripEvaluationRequest>
>;

export type CheckV2RejectsMissingPrice = Assert<
  Assignable<V2CommonRequest, V2TripEvaluationRequest> extends false
    ? true
    : false
>;

export type CheckV2RejectsBothPrices = Assert<
  Assignable<V2BothPricesRequest, V2TripEvaluationRequest> extends false
    ? true
    : false
>;

// V2 physical-energy responses must have required discriminators.

export type CheckV2GasolineDiscriminator = Assert<
  Assignable<V2GasolineConsumptionResponse["energy_type"], "gasoline">
>;

export type CheckV2ElectricDiscriminator = Assert<
  Assignable<V2ElectricConsumptionResponse["energy_type"], "electricity">
>;

export type CheckV2HasTypedConsumption = Assert<
  "consumption" extends keyof V2EnergyEstimateResponse ? true : false
>;
