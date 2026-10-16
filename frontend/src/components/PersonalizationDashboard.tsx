import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiRequestError } from "../api/tripEvaluations";
import {
  createSavedVehicle,
  deleteSavedVehicle,
  getSavedVehicles,
  getUserPreferences,
  updateUserPreferences,
  type SavedVehicle,
  type UserPreferences,
} from "../api/v2Resources";
import type { VehicleCatalogConfiguration } from "../api/vehicleCatalog";
import {
  formatVehicleConfiguration,
  formatVehicleEfficiency,
} from "../utils/vehicleDisplay";

import VehicleCatalogPicker from "./VehicleCatalogPicker";
import "./PersonalizationDashboard.css";

interface PersonalizationDashboardProps {
  onProfileChanged: () => void;
}

interface PersonalizationData {
  vehicles: SavedVehicle[];
  preferences: UserPreferences;
}

function vehicleTitle(vehicle: SavedVehicle): string {
  return `${vehicle.year} ${vehicle.make} ${vehicle.model}`;
}

function getVehicleSaveError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (
      error.status === 409 ||
      error.code === "vehicle_specification_unavailable"
    ) {
      return "This vehicle is listed in the catalog, but RouteValue cannot currently model its energy use. Choose another configuration.";
    }

    if (
      error.status === 404 ||
      error.code === "vehicle_configuration_not_found"
    ) {
      return "This vehicle configuration is no longer available. Select it again from the catalog.";
    }

    if (error.status === 502 || error.status === 503) {
      return "Vehicle data is temporarily unavailable. Please try saving again later.";
    }

    if (error.status === 401) {
      return "Your session has expired. Sign in again before saving a vehicle.";
    }
  }

  return "Could not save this vehicle. Please try again.";
}

export default function PersonalizationDashboard({
  onProfileChanged,
}: PersonalizationDashboardProps) {
  const [data, setData] = useState<PersonalizationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [retryVersion, setRetryVersion] = useState(0);

  const [valueOfTime, setValueOfTime] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const mutationInFlight = useRef(false);

  useEffect(() => {
    let active = true;

    void Promise.all([getSavedVehicles(), getUserPreferences()]).then(
      ([vehiclesResult, preferences]) => {
        if (!active) {
          return;
        }

        setData({
          vehicles: vehiclesResult.vehicles,
          preferences,
        });
        setValueOfTime(preferences.value_of_time_per_hour ?? "");
        setLoadError(false);
        setLoading(false);
      },
      () => {
        if (active) {
          setLoadError(true);
          setLoading(false);
        }
      },
    );

    return () => {
      active = false;
    };
  }, [retryVersion]);

  async function reloadData() {
    const [vehiclesResult, preferences] = await Promise.all([
      getSavedVehicles(),
      getUserPreferences(),
    ]);

    setData({
      vehicles: vehiclesResult.vehicles,
      preferences,
    });
    setValueOfTime(preferences.value_of_time_per_hour ?? "");
    setLoadError(false);
  }

  function retryLoading() {
    setLoading(true);
    setLoadError(false);
    setRetryVersion((current) => current + 1);
  }

  async function performMutation(
    name: string,
    operation: () => Promise<unknown>,
    successMessage: string,
    failureMessage: string,
  ): Promise<boolean> {
    if (mutationInFlight.current) {
      return false;
    }

    mutationInFlight.current = true;
    setBusyAction(name);
    setActionError(null);
    setNotice(null);

    try {
      await operation();

      setNotice(successMessage);
      onProfileChanged();

      try {
        await reloadData();
      } catch {
        setActionError(
          "Your change was saved, but the latest account data could not be loaded. Refresh the dashboard to verify it.",
        );
      }

      return true;
    } catch (error: unknown) {
      setActionError(
        name === "save-vehicle" ? getVehicleSaveError(error) : failureMessage,
      );
      return false;
    } finally {
      mutationInFlight.current = false;
      setBusyAction(null);
    }
  }

  async function handleSaveVehicle(
    configuration: VehicleCatalogConfiguration,
  ): Promise<boolean> {
    const alreadySaved = data?.vehicles.some(
      (vehicle) =>
        vehicle.source === configuration.source &&
        vehicle.source_id === configuration.source_id,
    );

    if (alreadySaved) {
      setNotice(null);
      setActionError(
        "This exact vehicle configuration is already in your garage.",
      );
      return false;
    }

    return performMutation(
      "save-vehicle",
      () => createSavedVehicle(configuration),
      "Vehicle saved to your account.",
      "Could not save this vehicle. Please try again.",
    );
  }

  async function handleSetDefault(vehicleId: string | null) {
    await performMutation(
      "default-vehicle",
      () => updateUserPreferences({ default_vehicle_id: vehicleId }),
      vehicleId ? "Default vehicle updated." : "Default vehicle cleared.",
      "Could not update your default vehicle.",
    );
  }

  async function handleDeleteVehicle(vehicleId: string) {
    const deleted = await performMutation(
      "delete-vehicle",
      () => deleteSavedVehicle(vehicleId),
      "Vehicle deleted from your account.",
      "Could not delete the vehicle. Please try again.",
    );

    if (deleted) {
      setConfirmDeleteId(null);
    }
  }

  async function handleSavePreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalized = valueOfTime.trim();

    if (normalized !== "" && !/^\d+(?:\.\d+)?$/.test(normalized)) {
      setActionError(
        "Enter a non-negative decimal value of time, or leave it blank to clear it.",
      );
      return;
    }

    await performMutation(
      "value-of-time",
      () =>
        updateUserPreferences({
          value_of_time_per_hour: normalized || null,
        }),
      "Value of time saved.",
      "Could not save your value of time.",
    );
  }

  if (loading) {
    return (
      <section className="m9-dashboard" role="status">
        Loading your vehicles and preferences...
      </section>
    );
  }

  if (loadError && data === null) {
    return (
      <section className="m9-dashboard">
        <h3>Personalization unavailable</h3>
        <p role="alert">Could not load your saved vehicles or preferences.</p>
        <button
          type="button"
          className="v2-secondary-button"
          onClick={retryLoading}
        >
          Retry dashboard
        </button>
      </section>
    );
  }

  if (data === null) {
    return null;
  }

  const busy = busyAction !== null;
  const defaultVehicleId = data.preferences.default_vehicle_id;

  return (
    <div className="m9-dashboard">
      <section className="m9-section" aria-labelledby="m9-preferences-title">
        <div className="m9-section-heading">
          <div>
            <p className="eyebrow">Personal settings</p>
            <h3 id="m9-preferences-title">Your value of time</h3>
          </div>
        </div>

        <p className="muted">
          RouteValue uses this amount to convert time spent driving into a
          monetary cost when comparing routes.
        </p>

        <form
          className="m9-preferences-form"
          onSubmit={(event) => void handleSavePreferences(event)}
        >
          <label className="field field-medium">
            <span>Value of time ($/hour)</span>
            <input
              type="text"
              inputMode="decimal"
              value={valueOfTime}
              onChange={(event) => setValueOfTime(event.target.value)}
              placeholder="e.g. 25.00"
              disabled={busy}
            />
          </label>

          <button className="v2-primary-button" type="submit" disabled={busy}>
            Save preferences
          </button>
        </form>

        <p className="m9-note">
          Leave the field blank and save to clear this preference. Decimal
          values are sent directly to the backend without JavaScript
          floating-point conversion.
        </p>
      </section>

      <section className="m9-section" aria-labelledby="m9-saved-vehicles-title">
        <div className="m9-section-heading">
          <div>
            <p className="eyebrow">Your garage</p>
            <h3 id="m9-saved-vehicles-title">Saved vehicles</h3>
          </div>

          <span className="m9-vehicle-count">{data.vehicles.length} saved</span>
        </div>

        {data.vehicles.length === 0 ? (
          <p className="m9-note">
            No vehicles saved yet. Add your first vehicle below.
          </p>
        ) : (
          <ul className="m9-vehicle-list">
            {data.vehicles.map((vehicle) => {
              const isDefault = vehicle.id === defaultVehicleId;
              const confirming = confirmDeleteId === vehicle.id;

              return (
                <li className="m9-vehicle-item" key={vehicle.id}>
                  <div className="m9-vehicle-details">
                    <div className="m9-vehicle-heading">
                      <strong>{vehicleTitle(vehicle)}</strong>
                      {isDefault && (
                        <span className="m9-default-label">Default</span>
                      )}
                    </div>

                    <p>{formatVehicleConfiguration(vehicle.configuration)}</p>

                    <p className="m9-efficiency">
                      {formatVehicleEfficiency(vehicle.specification)}
                    </p>
                  </div>

                  <div className="m9-vehicle-actions">
                    {!isDefault && (
                      <button
                        type="button"
                        className="v2-secondary-button"
                        disabled={busy}
                        onClick={() => void handleSetDefault(vehicle.id)}
                      >
                        Set as default
                      </button>
                    )}

                    {confirming ? (
                      <div className="m9-confirm-actions">
                        <span>Delete this vehicle?</span>
                        <button
                          type="button"
                          className="v2-secondary-button"
                          disabled={busy}
                          onClick={() => void handleDeleteVehicle(vehicle.id)}
                        >
                          Confirm delete
                        </button>
                        <button
                          type="button"
                          className="v2-secondary-button"
                          disabled={busy}
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="v2-secondary-button"
                        disabled={busy}
                        onClick={() => setConfirmDeleteId(vehicle.id)}
                        aria-label={`Delete ${vehicleTitle(vehicle)}`}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {defaultVehicleId !== null && (
          <button
            type="button"
            className="v2-secondary-button"
            disabled={busy}
            onClick={() => void handleSetDefault(null)}
          >
            Clear default vehicle
          </button>
        )}
      </section>

      <section className="m9-section" aria-labelledby="m9-add-vehicle-title">
        <div className="m9-section-heading">
          <div>
            <p className="eyebrow">Vehicle catalog</p>
            <h3 id="m9-add-vehicle-title">Add a vehicle</h3>
          </div>
        </div>

        <p className="muted">
          Choose the exact vehicle configuration so RouteValue can retrieve the
          correct gasoline or electric specification.
        </p>

        <VehicleCatalogPicker onSave={handleSaveVehicle} disabled={busy} />
      </section>

      {notice && (
        <p role="status" className="m9-feedback m9-success">
          {notice}
        </p>
      )}

      {actionError && (
        <div className="m9-feedback m9-error">
          <p role="alert">{actionError}</p>
          <button
            type="button"
            className="v2-secondary-button"
            disabled={busy}
            onClick={retryLoading}
          >
            Refresh account data
          </button>
        </div>
      )}
    </div>
  );
}
