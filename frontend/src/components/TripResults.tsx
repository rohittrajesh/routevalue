import type {
  RouteResponse,
  TripEvaluationResponse,
} from "../types/api";

import {
  formatDecisionReason,
  formatDistance,
  formatDuration,
  formatEligibilityReason,
  formatMoney,
} from "../utils/format";

interface TripResultsProps {
  result: TripEvaluationResponse;
}

function routesMatch(
  first: RouteResponse,
  second: RouteResponse,
): boolean {
  return (
    first.distance_meters === second.distance_meters &&
    first.duration_seconds === second.duration_seconds &&
    first.toll_cost === second.toll_cost
  );
}

function TripResults({ result }: TripResultsProps) {
  const recommendedRoute = result.decision.recommended_route;

  const recommendedIndex =
    recommendedRoute === null
      ? -1
      : result.route_evaluations.findIndex((evaluation) =>
          routesMatch(evaluation.route, recommendedRoute),
        );

  const recommendedEvaluation =
    recommendedIndex >= 0
      ? result.route_evaluations[recommendedIndex]
      : null;

  return (
    <section
      className="results-section"
      aria-labelledby="results-title"
      aria-live="polite"
    >
      <div className="results-heading">
        <div>
          <p className="eyebrow">Route comparison</p>

          <h2 id="results-title">Your routes</h2>

          <p className="results-subtitle">
            Compared using your fuel costs and the value of your travel time.
          </p>
        </div>

        <span className="route-count">
          {result.decision.eligible_count} of{" "}
          {result.decision.candidate_count} eligible
        </span>
      </div>

      {recommendedEvaluation !== null ? (
        <div className="recommendation-summary">
          <div className="recommendation-copy">
            <span className="recommendation-label">
              RouteValue recommendation
            </span>

            <strong>Route {recommendedIndex + 1} is your best match.</strong>

            <p>
              {formatDecisionReason(result.decision.reason)}
            </p>
          </div>

          {recommendedEvaluation.cost_breakdown !== null && (
            <div className="recommendation-cost">
              <span>Personalized cost</span>

              <strong>
                {formatMoney(
                  recommendedEvaluation.cost_breakdown.generalized_cost,
                )}
              </strong>
            </div>
          )}
        </div>
      ) : (
        <div className="recommendation-summary recommendation-unavailable">
          <div className="recommendation-copy">
            <span className="recommendation-label">
              No recommendation available
            </span>

            <strong>
              RouteValue does not have enough data to score these routes.
            </strong>
          </div>
        </div>
      )}

      <div className="route-grid">
        {result.route_evaluations.map((evaluation, index) => {
          const recommended =
            recommendedRoute !== null &&
            routesMatch(evaluation.route, recommendedRoute);

          return (
            <article
              className={`route-card ${
                recommended ? "recommended-route" : ""
              }`}
              aria-label={`Route ${index + 1}${
                recommended ? ", recommended" : ""
              }`}
              key={index}
            >
              <div className="route-card-header">
                <div>
                  <p className="route-number">
                    Route {index + 1}
                  </p>

                  <h3>
                    {formatDuration(
                      evaluation.route.duration_seconds,
                    )}
                  </h3>

                  <p className="route-distance">
                    {formatDistance(
                      evaluation.route.distance_meters,
                    )}
                  </p>
                </div>

                {recommended && (
                  <span className="recommended-badge">
                    Best match
                  </span>
                )}
              </div>

              {evaluation.cost_breakdown !== null ? (
                <>
                  <div className="personalized-cost-hero">
                    <span>Personalized route cost</span>

                    <strong>
                      {formatMoney(
                        evaluation.cost_breakdown.generalized_cost,
                      )}
                    </strong>

                    <small>
                      Fuel + tolls + value of your travel time
                    </small>
                  </div>

                  <dl className="cost-details">
                    <div>
                      <dt>Fuel</dt>
                      <dd>
                        {evaluation.energy_estimate === null
                          ? "Unavailable"
                          : formatMoney(
                              evaluation.energy_estimate.cost,
                            )}
                      </dd>
                    </div>

                    <div>
                      <dt>Tolls</dt>
                      <dd>
                        {formatMoney(
                          evaluation.route.toll_cost,
                        )}
                      </dd>
                    </div>

                    <div className="cost-subtotal">
                      <dt>Direct monetary cost</dt>
                      <dd>
                        {formatMoney(
                          evaluation.cost_breakdown.monetary_cost,
                        )}
                      </dd>
                    </div>

                    <div>
                      <dt>Value of travel time</dt>
                      <dd>
                        {formatMoney(
                          evaluation.cost_breakdown.time_cost,
                        )}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <div className="route-unavailable">
                  <strong>Unable to score this route</strong>

                  <span>
                    {formatEligibilityReason(
                      evaluation.eligibility.reason,
                    )}
                  </span>
                </div>
              )}
            </article>
          );
        })}
      </div>

      <p className="rounding-note">
        Cost components are displayed to the nearest cent. RouteValue uses
        full-precision values when calculating the personalized total.
      </p>
    </section>
  );
}

export default TripResults;