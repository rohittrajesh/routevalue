
/**
 * Compile-time assertions for RouteValue V1/V2 evaluation contracts.
 *
 * TypeScript checks these assertions during `npm run build`.
 * No runtime code or network calls are generated.
 */

import type { paths } from "../api/generated/schema";
import type {
  GasolineInputs,
  TripEvaluationRequest,
  TripEvaluationResponse,
  V2GasolineInputs,
  V2TripEvaluationRequest,
} from "./api";

type Assert<Condition extends true> = Condition;

type Assignable<Source, Destination> =
  [Source] extends [Destination] ? true : false;

type V1Operation = paths["/trip-evaluations"]["post"];

type V2Operation = paths["/api/v2/trip-evaluations"]["post"];

type V1RequestBody =
  V1Operation["requestBody"]["content"]["application/json"];

type V2RequestBody =
  V2Operation["requestBody"]["content"]["application/json"];

type V1Success =
  V1Operation["responses"][200]["content"]["application/json"];

type V2Success =
  V2Operation["responses"][200]["content"]["application/json"];

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
  Assignable<V2Success, TripEvaluationResponse>
>;

export type CheckV1StillHasEfficiency = Assert<
  "fuel_efficiency_mpg" extends keyof GasolineInputs ? true : false
>;

export type CheckV1StillHasValueOfTime = Assert<
  "value_of_time_per_hour" extends keyof TripEvaluationRequest
    ? true
    : false
>;

export type CheckV2HasNoClientValueOfTime = Assert<
  "value_of_time_per_hour" extends keyof V2TripEvaluationRequest
    ? false
    : true
>;

export type CheckV2HasNoClientUserId = Assert<
  "user_id" extends keyof V2TripEvaluationRequest
    ? false
    : true
>;

export type CheckV2HasNoClientEfficiency = Assert<
  "fuel_efficiency_mpg" extends keyof V2GasolineInputs
    ? false
    : true
>;

export type CheckV2HasNoClientFuelGrade = Assert<
  "fuel_grade" extends keyof V2GasolineInputs ? false : true
>;

export type CheckV2PriceIsDecimalString = Assert<
  Assignable<V2GasolineInputs["fuel_price_per_gallon"], string>
>;

export type CheckV2HasOptionalVehicleSelection = Assert<
  Assignable<
    V2TripEvaluationRequest["saved_vehicle_id"],
    string | null | undefined
  >
>;
