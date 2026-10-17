
import { useState } from "react";

import type {
  ResolvedLocationInput,
  RouteResponse,
  V2EnergyConsumptionResponse,
  V2TripEvaluationResponse,
} from "../types/api";
import {
  formatDecisionReason,
  formatDistance,
  formatDuration,
  formatEligibilityReason,
  formatMoney,
} from "../utils/format";
import RouteMap from "./RouteMap";
import "./V2TripResults.css";

interface V2TripResultsProps {
  result: V2TripEvaluationResponse;
  origin: ResolvedLocationInput;
  destination: ResolvedLocationInput;
  evaluatedVehicleName: string;
}

function routesMatch(first: RouteResponse, second: RouteResponse): boolean {
  return (
    first.distance_meters === second.distance_meters &&
    first.duration_seconds === second.duration_seconds &&
    first.toll_cost === second.toll_cost
  );
}

function formatConsumption(consumption: V2EnergyConsumptionResponse): string {
  if (consumption.energy_type === "gasoline") {
    return `${Number(consumption.gallons).toFixed(2)} gal`;
  }

  return `${Number(consumption.kilowatt_hours).toFixed(2)} kWh`;
}

function terrainFallbackDescription(reason: string): string {
  switch (reason) {
    case "acquisition_disabled":
      return "Elevation sampling is currently disabled, so terrain adjustments cannot be calculated.";
    case "elevation_unavailable":
      return "Elevation observations were unavailable for at least one route.";
    case "untrusted_geometry":
      return "The available route geometry was not reliable enough for terrain calculations.";
    case "insufficient_coverage":
      return "At least one route did not have sufficient usable elevation-data coverage.";
    case "invalid_route_distance":
      return "At least one route had an unusable distance for terrain calculations.";
    case "missing_vehicle_mass":
      return "The selected vehicle does not have verified mass data required for terrain energy calculations.";
    case "safety_fallback":
      return "RouteValue selected the baseline energy model to preserve a consistent comparison.";
    default:
      return "An additional terrain-related fallback condition was reported.";
  }
}

function terrainAcquisitionDescription(status: string | undefined): string {
  switch (status) {
    case "complete":
      return "Complete";
    case "partial":
      return "Partial";
    case "unavailable":
      return "Unavailable";
    default:
      return "Not reported";
  }
}

function terrainCoverageDescription(
  fraction: string | number | null | undefined,
): string {
  if (fraction === null || fraction === undefined) {
    return "Not reported";
  }

  const numeric = Number(fraction);

  if (!Number.isFinite(numeric) || numeric < 0 || numeric > 1) {
    return "Not reported";
  }

  return `${Math.round(numeric * 100)}%`;
}

export default function V2TripResults({
  result,
  origin,
  destination,
  evaluatedVehicleName,
}: V2TripResultsProps) {
  const [selectedRouteIndex, setSelectedRouteIndex] = useState<number | null>(
    null,
  );

  const recommendedRoute = result.decision.recommended_route;

  const recommendedIndex =
    recommendedRoute === null
      ? -1
      : result.route_evaluations.findIndex((evaluation) =>
          routesMatch(evaluation.route, recommendedRoute),
        );

  const recommendedEvaluation =
    recommendedIndex >= 0 ? result.route_evaluations[recommendedIndex] : null;

  const terrain = result.terrain_status;

  const terrainRoutesMatch =
    terrain !== null &&
    terrain !== undefined &&
    terrain.route_acquisition_statuses.length ===
      result.route_evaluations.length &&
    terrain.route_coverage_fractions.length ===
      result.route_evaluations.length;

  return (
    <section
      className="m9-trip-result"
      aria-labelledby="m9-trip-results-heading"
      aria-live="polite"
    >
      <p className="eyebrow">Route evaluation</p>
      <h4 id="m9-trip-results-heading">Your route comparison</h4>

      <p className="m9-note">
        Evaluated with {evaluatedVehicleName}. {result.decision.eligible_count}{" "}
        of {result.decision.candidate_count} routes eligible.
      </p>

      {recommendedEvaluation !== null ? (
        <div className="m9-trip-recommendation">
          <strong>Recommended: Route {recommendedIndex + 1}</strong>

          <span>
            {formatDuration(recommendedEvaluation.route.duration_seconds)}
            {" · "}
            {formatDistance(recommendedEvaluation.route.distance_meters)}
          </span>

          <span>
            Personalized cost:{" "}
            {formatMoney(
              recommendedEvaluation.cost_breakdown?.generalized_cost ?? null,
            )}
          </span>

          <p>{formatDecisionReason(result.decision.reason)}</p>
        </div>
      ) : (
        <p className="m9-trip-notice">
          {result.decision.candidate_count === 0
            ? "No routes were returned for this trip."
            : "No eligible recommendation is available. Review the route details below."}
        </p>
      )}

      {result.route_evaluations.length > 0 && (
        <section
          className="m9-v2-terrain-panel"
          aria-label="Terrain calculation status"
        >
          <p className="eyebrow">Terrain-aware energy</p>

          {terrain === null || terrain === undefined ? (
            <>
              <h5>Terrain status unavailable</h5>
              <p>
                This evaluation did not provide terrain diagnostics. RouteValue
                cannot confirm whether terrain adjustments were applied.
              </p>
            </>
          ) : (
            <>
              <h5>
                {terrain.terrain_applied
                  ? "Terrain adjustments applied"
                  : "Baseline energy estimates used"}
              </h5>

              <p>
                {terrain.terrain_applied
                  ? "RouteValue applied terrain-aware energy corrections to the evaluated routes."
                  : "RouteValue evaluated these routes using the standard vehicle energy model without terrain corrections."}
              </p>

              {!terrain.terrain_applied &&
                terrain.fallback_reasons.length > 0 && (
                  <ul className="m9-v2-terrain-reasons">
                    {terrain.fallback_reasons.map((reason, index) => (
                      <li key={`${reason}-${index}`}>
                        {terrainFallbackDescription(reason)}
                      </li>
                    ))}
                  </ul>
                )}

              {terrainRoutesMatch ? (
                <div className="m9-v2-terrain-routes">
                  <strong>Elevation data by route</strong>

                  <dl aria-label="Per-route terrain observations">
                    {result.route_evaluations.map((_, index) => (
                      <div key={index}>
                        <dt>Route {index + 1}</dt>
                        <dd>
                          Elevation:{" "}
                          {terrainAcquisitionDescription(
                            terrain.route_acquisition_statuses[index],
                          )}
                          {" · "}
                          Usable coverage:{" "}
                          {terrainCoverageDescription(
                            terrain.route_coverage_fractions[index],
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : (
                <p className="m9-v2-terrain-warning">
                  Per-route terrain observations could not be aligned with the
                  evaluated routes.
                </p>
              )}
            </>
          )}
        </section>
      )}

      {result.route_evaluations.length > 0 && (
        <RouteMap
          routeEvaluations={result.route_evaluations}
          recommendedRouteIndex={recommendedIndex}
          selectedRouteIndex={selectedRouteIndex}
          origin={origin}
          destination={destination}
        />
      )}

      <ul className="m9-trip-route-list m9-v2-result-list">
        {result.route_evaluations.map((evaluation, index) => {
          const isRecommended = index === recommendedIndex;
          const isSelected = index === selectedRouteIndex;

          const hasGeometry =
            evaluation.geometry !== null &&
            evaluation.geometry !== undefined &&
            evaluation.geometry.points.length >= 2;

          return (
            <li
              key={index}
              className={[
                "m9-v2-result-card",
                isRecommended ? "m9-v2-result-recommended" : "",
                isSelected ? "m9-v2-result-selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-label={`Route ${index + 1}${isRecommended ? ", recommended" : ""}`}
            >
              <div className="m9-v2-result-header">
                <strong>Route {index + 1}</strong>

                {isRecommended && (
                  <span className="m9-v2-best-label">Best match</span>
                )}
              </div>

              <span>{formatDuration(evaluation.route.duration_seconds)}</span>
              <span>{formatDistance(evaluation.route.distance_meters)}</span>

              {evaluation.cost_breakdown !== null ? (
                <dl className="m9-v2-cost-details">
                  <div>
                    <dt>Personalized total</dt>
                    <dd>
                      <strong>
                        {formatMoney(
                          evaluation.cost_breakdown.generalized_cost,
                        )}
                      </strong>
                    </dd>
                  </div>

                  <div>
                    <dt>Energy cost</dt>
                    <dd>
                      {formatMoney(evaluation.energy_estimate?.cost ?? null)}
                    </dd>
                  </div>

                  <div>
                    <dt>Tolls</dt>
                    <dd>{formatMoney(evaluation.route.toll_cost)}</dd>
                  </div>

                  <div>
                    <dt>Travel time cost</dt>
                    <dd>{formatMoney(evaluation.cost_breakdown.time_cost)}</dd>
                  </div>

                  <div>
                    <dt>Direct monetary cost</dt>
                    <dd>
                      {formatMoney(evaluation.cost_breakdown.monetary_cost)}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="m9-v2-unavailable">
                  {formatEligibilityReason(evaluation.eligibility.reason)}
                </p>
              )}

              {evaluation.energy_estimate?.consumption != null && (
                <p className="m9-v2-consumption">
                  Energy used:{" "}
                  {formatConsumption(evaluation.energy_estimate.consumption)}
                </p>
              )}

              {hasGeometry && (
                <button
                  type="button"
                  className="v2-secondary-button m9-v2-map-button"
                  aria-label={`View Route ${index + 1} on map`}
                  aria-pressed={isSelected}
                  onClick={() => {
                    setSelectedRouteIndex((current) =>
                      current === index ? null : index,
                    );
                  }}
                >
                  {isSelected ? "Show all routes" : "View on map"}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <p className="m9-note">
        Displayed costs and energy quantities are rounded for readability.
        RouteValue uses full precision for route comparisons. The map displays
        available overview route geometry; it does not represent measured road
        grade or elevation.
      </p>
    </section>
  );
}
