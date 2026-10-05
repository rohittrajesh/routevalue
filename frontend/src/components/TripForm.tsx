import type { FormEvent } from "react";

import type {
  GasolineGrade,
  TripEvaluationRequest,
} from "../types/api";

interface TripFormProps {
  onSubmit: (request: TripEvaluationRequest) => void;
  isSubmitting: boolean;
}

function TripForm({
  onSubmit,
  isSubmitting,
}: TripFormProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);

    const request: TripEvaluationRequest = {
      origin: String(form.get("origin") ?? ""),
      destination: String(form.get("destination") ?? ""),
      value_of_time_per_hour: String(
        form.get("value_of_time_per_hour") ?? "",
      ),
      gasoline: {
        fuel_efficiency_mpg: String(
          form.get("fuel_efficiency_mpg") ?? "",
        ),
        fuel_grade: String(
          form.get("fuel_grade") ?? "regular",
        ) as GasolineGrade,
        fuel_price_per_gallon: String(
          form.get("fuel_price_per_gallon") ?? "",
        ),
      },
    };

    onSubmit(request);
  }

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">01</span>
          <div>
            <h3>Your trip</h3>
            <p>Where are you going?</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>Origin</span>
            <input
              name="origin"
              type="text"
              placeholder="UC San Diego"
              autoComplete="street-address"
              required
            />
          </label>

          <label className="field">
            <span>Destination</span>
            <input
              name="destination"
              type="text"
              placeholder="San Diego International Airport"
              autoComplete="street-address"
              required
            />
          </label>
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
          RouteValue compares travel time, fuel, and tolls using your
          preferences.
        </p>

        <button
  className="primary-button"
  type="submit"
  disabled={isSubmitting}
>
  {isSubmitting ? "Comparing routes..." : "Compare routes"}
</button>
      </div>
    </form>
  );
}

export default TripForm;