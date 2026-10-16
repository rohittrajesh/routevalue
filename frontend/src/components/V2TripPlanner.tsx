import { useRef, useState, type FormEvent } from "react";

import { ApiRequestError } from "../api/tripEvaluations";
import {
  evaluateV2Trip,
  type SavedVehicle,
  type UserPreferences,
} from "../api/v2Resources";
import type {
  ResolvedLocationInput,
  V2TripEvaluationResponse,
} from "../types/api";
import {
  formatDecisionReason,
  formatDistance,
  formatDuration,
  formatMoney,
} from "../utils/format";
import {
  buildV2TripRequest,
  isValidNonnegativeDecimal,
  type GasolinePricingMode,
} from "../utils/v2TripRequest";
import PlaceAutocompleteInput from "./PlaceAutocompleteInput";
import "./V2TripPlanner.css";

interface V2TripPlannerProps {
  vehicles: SavedVehicle[];
  preferences: UserPreferences;
}

function vehicleName(vehicle: SavedVehicle): string {
  return `${vehicle.year} ${vehicle.make} ${vehicle.model}`;
}

function isAutomaticPricingFailure(error: ApiRequestError): boolean {
  return [
    "gasoline_price_unavailable",
    "gasoline_price_stale",
    "gasoline_price_provider_unavailable",
    "gasoline_price_invalid",
  ].includes(error.code);
}

function tripErrorMessage(error: unknown): string {
  if (!(error instanceof ApiRequestError)) {
    return "RouteValue could not evaluate this trip. Please try again.";
  }

  if (isAutomaticPricingFailure(error)) {
    return `${error.message} You can switch to a manual gasoline price without losing your trip.`;
  }

  if (error.code === "authentication_required") {
    return "Your session has expired. Please sign in again.";
  }

  if (
    error.code === "value_of_time_not_configured" ||
    error.code === "default_vehicle_not_configured" ||
    error.code === "default_vehicle_unavailable" ||
    error.code === "saved_vehicle_not_found"
  ) {
    return `${error.message} Check your saved profile above.`;
  }

  if (error.code === "energy_input_mismatch") {
    return "The price type does not match the selected vehicle. Check the trip inputs.";
  }

  return error.message;
}

function displayConsumption(
  consumption: NonNullable<
    NonNullable<
      V2TripEvaluationResponse["route_evaluations"][number]["energy_estimate"]
    >["consumption"]
  >,
): string {
  if (consumption.energy_type === "gasoline") {
    return `${Number(consumption.gallons).toFixed(2)} gal`;
  }
  return `${Number(consumption.kilowatt_hours).toFixed(2)} kWh`;
}

export default function V2TripPlanner({
  vehicles,
  preferences,
}: V2TripPlannerProps) {
  const [origin, setOrigin] = useState<ResolvedLocationInput | null>(null);
  const [destination, setDestination] = useState<ResolvedLocationInput | null>(
    null,
  );
  const [explicitVehicleId, setExplicitVehicleId] = useState<string | null>(
    null,
  );
  const [gasolinePricingMode, setGasolinePricingMode] =
    useState<GasolinePricingMode>("automatic");
  const [gasolinePrice, setGasolinePrice] = useState("");
  const [electricityPrice, setElectricityPrice] = useState("");
  const [result, setResult] = useState<V2TripEvaluationResponse | null>(null);
  const [evaluatedVehicleName, setEvaluatedVehicleName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inFlight = useRef(false);
  const requestVersion = useRef(0);

  const fallbackId =
    vehicles.find((vehicle) => vehicle.id === preferences.default_vehicle_id)
      ?.id ??
    vehicles[0]?.id ??
    "";

  const selectedId =
    explicitVehicleId !== null &&
    vehicles.some((vehicle) => vehicle.id === explicitVehicleId)
      ? explicitVehicleId
      : fallbackId;

  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === selectedId);
  const hasValueOfTime = preferences.value_of_time_per_hour !== null;
  const priceIsValid =
    selectedVehicle?.specification.powertrain === "bev"
      ? isValidNonnegativeDecimal(electricityPrice)
      : gasolinePricingMode === "automatic" ||
        isValidNonnegativeDecimal(gasolinePrice);
  const ready =
    origin !== null &&
    destination !== null &&
    selectedVehicle !== undefined &&
    hasValueOfTime &&
    priceIsValid;

  function invalidateResult() {
    requestVersion.current += 1;
    setResult(null);
    setError(null);
  }

  function handleOrigin(location: ResolvedLocationInput | null) {
    setOrigin(location);
    invalidateResult();
  }

  function handleDestination(location: ResolvedLocationInput | null) {
    setDestination(location);
    invalidateResult();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (
      inFlight.current ||
      !ready ||
      origin === null ||
      destination === null ||
      selectedVehicle === undefined
    ) {
      return;
    }

    const version = ++requestVersion.current;
    inFlight.current = true;
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const request = buildV2TripRequest({
        origin,
        destination,
        vehicle: selectedVehicle,
        gasolinePricingMode,
        gasolinePrice,
        electricityPrice,
      });
      const response = await evaluateV2Trip(request);
      if (version === requestVersion.current) {
        setEvaluatedVehicleName(vehicleName(selectedVehicle));
        setResult(response);
      }
    } catch (caught: unknown) {
      if (version === requestVersion.current) {
        setError(caught);
      }
    } finally {
      inFlight.current = false;
      setIsSubmitting(false);
    }
  }

  const recommendedRoute = result?.decision.recommended_route;
  const recommendation = result?.route_evaluations.find(
    (evaluation) =>
      recommendedRoute !== null &&
      recommendedRoute !== undefined &&
      evaluation.route.distance_meters === recommendedRoute.distance_meters &&
      evaluation.route.duration_seconds === recommendedRoute.duration_seconds &&
      evaluation.route.toll_cost === recommendedRoute.toll_cost,
  );
  const showManualFallback =
    error instanceof ApiRequestError &&
    selectedVehicle?.specification.powertrain === "gasoline" &&
    gasolinePricingMode === "automatic" &&
    isAutomaticPricingFailure(error);

  return (
    <section className="m9-trip-panel" aria-labelledby="m9-trip-heading">
      <p className="eyebrow">Authenticated trip evaluation</p>
      <h3 id="m9-trip-heading">Plan a trip</h3>
      <p className="muted">
        Compare routes using your saved vehicle and value of travel time. The
        backend calculates energy consumption and personalized costs.
      </p>

      {vehicles.length === 0 && (
        <p role="alert" className="m9-trip-notice">
          Save a vehicle in your garage before comparing routes.
        </p>
      )}
      {!hasValueOfTime && (
        <p role="alert" className="m9-trip-notice">
          Save your value of time in Personal settings before comparing routes.
        </p>
      )}

      <form
        className="m9-trip-form"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="m9-trip-fields">
          <PlaceAutocompleteInput
            label="Origin"
            placeholder="Choose a starting location"
            onLocationChange={handleOrigin}
          />
          <PlaceAutocompleteInput
            label="Destination"
            placeholder="Choose a destination"
            onLocationChange={handleDestination}
          />
        </div>

        <div className="m9-trip-fields">
          <label className="field">
            <span>Vehicle for this trip</span>
            <select
              value={selectedId}
              onChange={(event) => {
                setExplicitVehicleId(event.target.value);
                invalidateResult();
              }}
              disabled={isSubmitting || vehicles.length === 0}
            >
              {vehicles.length === 0 && (
                <option value="">Save a vehicle first</option>
              )}
              {vehicles.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicleName(vehicle)}
                  {vehicle.id === preferences.default_vehicle_id
                    ? " (default)"
                    : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="m9-trip-profile-summary">
            <span>Saved value of time</span>
            <strong>
              {preferences.value_of_time_per_hour === null
                ? "Not configured"
                : `${formatMoney(preferences.value_of_time_per_hour)}/hour`}
            </strong>
            <small>Manage this in Personal settings above.</small>
          </div>
        </div>

        {selectedVehicle?.specification.powertrain === "gasoline" && (
          <fieldset className="m9-trip-price-section">
            <legend>Gasoline price</legend>
            <label className="m9-trip-choice">
              <input
                type="radio"
                name="gasoline-pricing"
                checked={gasolinePricingMode === "automatic"}
                onChange={() => {
                  setGasolinePricingMode("automatic");
                  invalidateResult();
                }}
                disabled={isSubmitting}
              />
              Automatic regional pricing (when available)
            </label>
            <label className="m9-trip-choice">
              <input
                type="radio"
                name="gasoline-pricing"
                checked={gasolinePricingMode === "manual"}
                onChange={() => {
                  setGasolinePricingMode("manual");
                  invalidateResult();
                }}
                disabled={isSubmitting}
              />
              Enter my price
            </label>
            {gasolinePricingMode === "manual" && (
              <label className="field field-medium">
                <span>Gasoline price ($/gallon)</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={gasolinePrice}
                  onChange={(event) => {
                    setGasolinePrice(event.target.value);
                    invalidateResult();
                  }}
                  placeholder="e.g. 4.50"
                  disabled={isSubmitting}
                  required
                />
              </label>
            )}
          </fieldset>
        )}

        {selectedVehicle?.specification.powertrain === "bev" && (
          <label className="field field-medium m9-trip-electric-price">
            <span>Electricity price ($/kWh)</span>
            <input
              type="text"
              inputMode="decimal"
              value={electricityPrice}
              onChange={(event) => {
                setElectricityPrice(event.target.value);
                invalidateResult();
              }}
              placeholder="e.g. 0.25"
              disabled={isSubmitting}
              required
            />
            <small>Use your charging electricity rate.</small>
          </label>
        )}

        <div className="m9-trip-actions">
          <button
            className="v2-primary-button"
            type="submit"
            disabled={!ready || isSubmitting}
          >
            {isSubmitting ? "Comparing routes..." : "Compare routes"}
          </button>
          {!ready && (
            <p className="m9-note">
              Select both location suggestions, a vehicle, and a valid energy
              price when required.
            </p>
          )}
        </div>
      </form>

      {error !== null && (
        <div className="m9-trip-error" role="alert">
          <p>{tripErrorMessage(error)}</p>
          {showManualFallback && (
            <button
              type="button"
              className="v2-secondary-button"
              onClick={() => {
                setGasolinePricingMode("manual");
                invalidateResult();
              }}
            >
              Use manual gasoline price
            </button>
          )}
        </div>
      )}

      {result !== null && (
        <section
          className="m9-trip-result"
          aria-labelledby="m9-trip-results-heading"
        >
          <p className="eyebrow">Route evaluation</p>
          <h4 id="m9-trip-results-heading">Your route comparison</h4>
          <p className="m9-note">
            Evaluated with {evaluatedVehicleName}.{" "}
            {result.decision.eligible_count} of{" "}
            {result.decision.candidate_count} routes eligible.
          </p>
          {recommendation !== undefined ? (
            <div className="m9-trip-recommendation">
              <strong>
                Recommended:{" "}
                {formatDuration(recommendation.route.duration_seconds)}
              </strong>
              <span>
                {formatDistance(recommendation.route.distance_meters)}
              </span>
              <span>
                Personalized cost:{" "}
                {formatMoney(
                  recommendation.cost_breakdown?.generalized_cost ?? null,
                )}
              </span>
              <p>{formatDecisionReason(result.decision.reason)}</p>
            </div>
          ) : (
            <p className="m9-trip-notice">
              No eligible route recommendation is available. Check route details
              below.
            </p>
          )}
          <ul className="m9-trip-route-list">
            {result.route_evaluations.map((evaluation, index) => (
              <li key={index}>
                <strong>Route {index + 1}</strong>
                <span>{formatDuration(evaluation.route.duration_seconds)}</span>
                <span>{formatDistance(evaluation.route.distance_meters)}</span>
                <span>
                  Total:{" "}
                  {formatMoney(
                    evaluation.cost_breakdown?.generalized_cost ?? null,
                  )}
                </span>
                <span>
                  Energy cost:{" "}
                  {formatMoney(evaluation.energy_estimate?.cost ?? null)}
                </span>
                {evaluation.energy_estimate?.consumption != null && (
                  <span>
                    Energy used:{" "}
                    {displayConsumption(evaluation.energy_estimate.consumption)}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="m9-note">
            Display values are rounded for readability; the backend retains full
            calculation precision. Map and terrain detail will be added in M9-E.
          </p>
        </section>
      )}
    </section>
  );
}
