import { useState } from "react";

import "./App.css";

import { evaluateTrip } from "./api/tripEvaluations";
import TripForm from "./components/TripForm";
import TripResults from "./components/TripResults";
import type {
  ResolvedLocationInput,
  TripEvaluationRequest,
  TripEvaluationResponse,
} from "./types/api";

interface EvaluatedLocations {
  origin: ResolvedLocationInput;
  destination: ResolvedLocationInput;
}

function App() {
  const [result, setResult] = useState<TripEvaluationResponse | null>(null);
  const [evaluatedLocations, setEvaluatedLocations] =
    useState<EvaluatedLocations | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleTripSubmit(request: TripEvaluationRequest) {
    setIsSubmitting(true);
    setError(null);
    setResult(null);
    setEvaluatedLocations(null);

    try {
      const tripResult = await evaluateTrip(request);

      setEvaluatedLocations({
        origin: request.origin,
        destination: request.destination,
      });

      setResult(tripResult);
    } catch (caughtError) {
      if (caughtError instanceof Error) {
        setError(caughtError.message);
      } else {
        setError("RouteValue could not evaluate this trip.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <a className="brand" href="/" aria-label="RouteValue home">
          RouteValue
        </a>

        <div className="hero-copy">
          <p className="eyebrow">Personalized route decisions</p>

          <h1>Choose the route that costs you less.</h1>

          <p className="hero-description">
            Compare travel time, fuel, and tolls using what your time is
            actually worth.
          </p>
        </div>
      </header>

      <section className="workspace" aria-labelledby="trip-title">
        <div className="primary-panel">
          <p className="eyebrow">Trip evaluation</p>

          <h2 id="trip-title">Plan a trip</h2>

          <p className="muted">
            Enter your trip and driving preferences to compare personalized
            route costs.
          </p>

          <TripForm onSubmit={handleTripSubmit} isSubmitting={isSubmitting} />

          {error !== null && (
            <div className="status-message error-message" role="alert">
              <strong>We couldn't evaluate this trip.</strong>
              <span>{error}</span>
            </div>
          )}
        </div>

        <aside className="summary-panel">
          <p className="eyebrow">RouteValue considers</p>

          <ul className="factor-list">
            <li>
              <span>Travel time</span>
              <strong>Your value of time</strong>
            </li>

            <li>
              <span>Fuel</span>
              <strong>Your vehicle</strong>
            </li>

            <li>
              <span>Tolls</span>
              <strong>Route-specific</strong>
            </li>
          </ul>
        </aside>
      </section>

      {result !== null && evaluatedLocations !== null && (
        <TripResults
          result={result}
          origin={evaluatedLocations.origin}
          destination={evaluatedLocations.destination}
        />
      )}
    </main>
  );
}

export default App;