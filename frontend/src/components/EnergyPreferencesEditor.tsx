import { useId, useState, type FormEvent } from "react";

import type { PreferencesUpdate, UserPreferences } from "../api/v2Resources";
import type { ResolvedLocationInput } from "../types/api";
import { isValidNonnegativeDecimal } from "../utils/v2TripRequest";
import PlaceAutocompleteInput from "./PlaceAutocompleteInput";

interface Props {
  preferences: UserPreferences;
  busy: boolean;
  onSave: (changes: PreferencesUpdate, message: string) => Promise<boolean>;
}

export default function EnergyPreferencesEditor({
  preferences,
  busy,
  onSave,
}: Props) {
  const rateId = useId();
  const [rate, setRate] = useState(preferences.electricity_price_per_kwh ?? "");
  const [market, setMarket] = useState<ResolvedLocationInput | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function saveRate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = rate.trim();
    if (value !== "" && !isValidNonnegativeDecimal(value)) {
      setError(
        "Enter a non-negative electricity rate, or leave it blank to clear it.",
      );
      return;
    }
    setError(null);
    await onSave(
      { electricity_price_per_kwh: value || null },
      value === "" ? "Electricity rate cleared." : "Electricity rate saved.",
    );
  }

  async function saveMarket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (market === null || market.display_name.length > 200) {
      setError(
        "Choose a city or purchasing area from the suggestions before saving.",
      );
      return;
    }
    setError(null);
    await onSave(
      {
        preferred_fuel_market: {
          display_name: market.display_name,
          latitude: market.latitude,
          longitude: market.longitude,
        },
      },
      "Fuel market saved.",
    );
  }

  return (
    <section
      className="m9-section"
      aria-labelledby="m9-energy-preferences-title"
    >
      <p className="eyebrow">Personal settings</p>
      <h3 id="m9-energy-preferences-title">Energy preferences</h3>
      <form
        className="m9-preferences-form"
        onSubmit={(event) => void saveRate(event)}
      >
        <div className="field field-medium">
          <label htmlFor={rateId}>Saved electricity rate ($/kWh)</label>
          <input
            id={rateId}
            aria-describedby={`${rateId}-help`}
            type="text"
            inputMode="decimal"
            value={rate}
            onChange={(event) => setRate(event.target.value)}
            disabled={busy}
          />
          <small id={`${rateId}-help`}>
            Used for all your EVs. Leave blank to clear; no rate is assumed.
          </small>
        </div>
        <button type="submit" className="v2-secondary-button" disabled={busy}>
          Save electricity rate
        </button>
      </form>
      <p className="m9-note">
        {preferences.electricity_price_per_kwh == null
          ? "No electricity rate saved."
          : `Saved rate: $${preferences.electricity_price_per_kwh}/kWh. Trips can use this without entering a price again.`}
      </p>
      <p>
        Fuel market:{" "}
        {preferences.preferred_fuel_market?.display_name ??
          "Trip origin (no preferred area saved)"}
      </p>
      <p className="m9-note">
        Choose the city or area where you usually buy gasoline. Your home
        address is not required. Regional pricing uses this area; clearing it
        restores trip-origin pricing.
      </p>
      <form
        className="m9-fuel-market-form"
        onSubmit={(event) => void saveMarket(event)}
      >
        <fieldset disabled={busy}>
          <legend>Preferred fuel market</legend>
          <PlaceAutocompleteInput
            label="Fuel purchasing area"
            placeholder="Choose a city or area"
            onLocationChange={setMarket}
          />
          <div className="m9-energy-actions">
            <button
              type="submit"
              className="v2-secondary-button"
              disabled={busy || market === null}
            >
              Save fuel market
            </button>
            <button
              type="button"
              className="v2-secondary-button"
              disabled={busy || preferences.preferred_fuel_market == null}
              onClick={() =>
                void onSave(
                  { preferred_fuel_market: null },
                  "Fuel market cleared. Automatic pricing will use the trip origin.",
                )
              }
            >
              Clear fuel market
            </button>
          </div>
        </fieldset>
      </form>
      {error !== null && <p role="alert">{error}</p>}
    </section>
  );
}
