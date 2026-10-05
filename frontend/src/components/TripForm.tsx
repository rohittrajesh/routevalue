import { useState, type FormEvent } from "react";

import type {
  GasolineGrade,
  ResolvedLocationInput,
  TripEvaluationRequest,
} from "../types/api";
import PlaceAutocompleteInput from "./PlaceAutocompleteInput";

interface TripFormProps {
  onSubmit: (request: TripEvaluationRequest) => void;
  isSubmitting: boolean;
}

function TripForm({ onSubmit, isSubmitting }: TripFormProps) {
  const [origin, setOrigin] = useState<ResolvedLocationInput | null>(null);

  const [destination, setDestination] = useState<ResolvedLocationInput | null>(
    null,
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (origin === null || destination === null) {
      return;
    }

    const form = new FormData(event.currentTarget);

    const request: TripEvaluationRequest = {
      origin,
      destination,
      value_of_time_per_hour: String(form.get("value_of_time_per_hour") ?? ""),
      gasoline: {
        fuel_efficiency_mpg: String(form.get("fuel_efficiency_mpg") ?? ""),
        fuel_grade: String(
          form.get("fuel_grade") ?? "regular",
        ) as GasolineGrade,
        fuel_price_per_gallon: String(form.get("fuel_price_per_gallon") ?? ""),
      },
    };

    onSubmit(request);
  }

  const locationsResolved = origin !== null && destination !== null;

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">01</span>

          <div>
            <h3>Your trip</h3>
            <p>Search for and select both locations.</p>
          </div>
        </div>

        <div className="field-grid">
          <PlaceAutocompleteInput
            label="Origin"
            placeholder="UC San Diego"
            onLocationChange={setOrigin}
          />

          <PlaceAutocompleteInput
            label="Destination"
            placeholder="San Diego International Airport"
            onLocationChange={setDestination}
          />
        </div>
      </div>

      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">02</span>

          <div>
            <h3>Your time</h3>
            <p>How much is an hour of your travel time worth?</p>
          </div>
        </div>

        <label className="field field-medium">
          <span>Value of time</span>

          <div className="input-with-unit">
            <span className="input-prefix">$</span>

            <input
              name="value_of_time_per_hour"
              type="number"
              min="0"
              step="0.01"
              placeholder="20.00"
              required
            />

            <span className="input-suffix">/ hour</span>
          </div>
        </label>
      </div>

      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">03</span>

          <div>
            <h3>Your vehicle</h3>
            <p>Used to estimate fuel cost for each route.</p>
          </div>
        </div>

        <div className="vehicle-grid">
          <label className="field">
            <span>Fuel efficiency</span>

            <div className="input-with-unit">
              <input
                name="fuel_efficiency_mpg"
                type="number"
                min="0.01"
                step="0.01"
                placeholder="30"
                required
              />

              <span className="input-suffix">MPG</span>
            </div>
          </label>

          <label className="field">
            <span>Gasoline grade</span>

            <select name="fuel_grade" defaultValue="regular">
              <option value="regular">Regular</option>
              <option value="midgrade">Midgrade</option>
              <option value="premium">Premium</option>
            </select>
          </label>

          <label className="field">
            <span>Gas price</span>

            <div className="input-with-unit">
              <span className="input-prefix">$</span>

              <input
                name="fuel_price_per_gallon"
                type="number"
                min="0"
                step="0.001"
                placeholder="4.50"
                required
              />

              <span className="input-suffix">/ gal</span>
            </div>
          </label>
        </div>
      </div>

      <div className="form-actions">
        <p>
          {locationsResolved
            ? "Both locations are resolved and ready for comparison."
            : "Select an autocomplete suggestion for both locations before comparing routes."}
        </p>

        <button
          className="primary-button"
          type="submit"
          disabled={isSubmitting || !locationsResolved}
        >
          {isSubmitting ? "Comparing routes..." : "Compare routes"}
        </button>
      </div>
    </form>
  );
}

export default TripForm;
