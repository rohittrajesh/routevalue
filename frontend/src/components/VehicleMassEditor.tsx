import { useState, type FormEvent } from "react";

import {
  updateSavedVehicleMass,
  type SavedVehicle,
  type VehicleMassUpdate,
} from "../api/v2Resources";
import { ApiRequestError } from "../api/tripEvaluations";

import "./VehicleMassEditor.css";

interface VehicleMassEditorProps {
  vehicle: SavedVehicle;
  disabled: boolean;
  onUpdated: () => Promise<void>;
}

function massDescription(vehicle: SavedVehicle): string {
  const mass = vehicle.vehicle_mass;

  if (!mass) {
    return "Vehicle mass not configured.";
  }

  const kilograms = Number(mass.kilograms);
  const pounds = kilograms * 2.2046226218487757;

  const measurement =
    mass.source === "epa_test_weight" ? "EPA test weight" : "Vehicle mass";

  return `${measurement}: approximately ${Math.round(pounds).toLocaleString()} lb`;
}

function sourceDescription(vehicle: SavedVehicle): string | null {
  const mass = vehicle.vehicle_mass;

  if (!mass) {
    return null;
  }

  const kind =
    mass.source === "manufacturer_curb_weight"
      ? "Manufacturer data"
      : mass.source === "epa_test_weight"
        ? "EPA test-weight data"
        : "User-provided curb weight";

  return mass.source_reference ? `${kind} · ${mass.source_reference}` : kind;
}

export default function VehicleMassEditor({
  vehicle,
  disabled,
  onUpdated,
}: VehicleMassEditorProps) {
  const [editing, setEditing] = useState(false);
  const [weight, setWeight] = useState("");
  const [unit, setUnit] = useState<"lb" | "kg">("lb");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const busy = saving || disabled;
  const mass = vehicle.vehicle_mass;

  async function submitUpdate(changes: VehicleMassUpdate) {
    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      await updateSavedVehicleMass(vehicle.id, changes);

      setEditing(false);
      setConfirmClear(false);
      setWeight("");
      setReference("");

      setNotice(
        changes.weight === null
          ? "Vehicle mass cleared."
          : "Vehicle mass saved.",
      );

      try {
        await onUpdated();
      } catch {
        setError(
          "Your change was saved, but account data could not be refreshed.",
        );
      }
    } catch (failure: unknown) {
      if (failure instanceof ApiRequestError) {
        if (failure.status === 404) {
          setError("This saved vehicle is no longer available.");
        } else if (failure.status === 422) {
          setError(
            "The weight, unit or source note was rejected. Please check your inputs.",
          );
        } else if (failure.status === 401) {
          setError("Your session has expired. Please sign in again.");
        } else {
          setError("Could not update vehicle mass. Please try again.");
        }
      } else {
        setError("Could not update vehicle mass. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const value = weight.trim();
    const source = reference.trim();

    if (!/^\d+(?:\.\d+)?$/.test(value)) {
      setError("Enter a positive decimal weight.");
      return;
    }

    if (!source) {
      setError("Enter where you found this curb weight.");
      return;
    }

    await submitUpdate({
      weight: value,
      unit,
      source_reference: source,
    });
  }

  return (
    <div className="m9-mass-editor">
      <p className="m9-mass-value">{massDescription(vehicle)}</p>
      <p className="m9-mass-help">
        Curb weight is optional and entered by you. Without it, RouteValue uses
        baseline energy estimates. Weight is never looked up automatically.
      </p>

      {sourceDescription(vehicle) && (
        <p className="m9-mass-source">{sourceDescription(vehicle)}</p>
      )}

      {!editing ? (
        <>
          <button
            type="button"
            className="v2-secondary-button"
            disabled={busy}
            onClick={() => {
              setEditing(true);
              setError(null);
              setNotice(null);
              setConfirmClear(false);
            }}
          >
            {mass ? "Update vehicle weight" : "Add vehicle weight"}
          </button>

          {mass && !confirmClear && (
            <button
              type="button"
              className="v2-secondary-button"
              disabled={busy}
              onClick={() => setConfirmClear(true)}
            >
              Clear vehicle weight
            </button>
          )}

          {mass && confirmClear && (
            <div className="m9-mass-actions">
              <span>Clear this vehicle's stored mass?</span>
              <button
                type="button"
                className="v2-secondary-button"
                disabled={busy}
                onClick={() => void submitUpdate({ weight: null })}
              >
                Confirm clear
              </button>
              <button
                type="button"
                className="v2-secondary-button"
                disabled={busy}
                onClick={() => setConfirmClear(false)}
              >
                Cancel clearing
              </button>
            </div>
          )}
        </>
      ) : (
        <form
          className="m9-mass-form"
          onSubmit={(event) => void handleSave(event)}
        >
          <div className="m9-mass-fields">
            <label className="field">
              <span>Curb weight</span>
              <input
                type="text"
                inputMode="decimal"
                maxLength={15}
                value={weight}
                onChange={(event) => setWeight(event.target.value)}
                placeholder="e.g. 3600"
                disabled={busy}
              />
            </label>

            <label className="field">
              <span>Unit</span>
              <select
                value={unit}
                onChange={(event) => setUnit(event.target.value as "lb" | "kg")}
                disabled={busy}
              >
                <option value="lb">Pounds (lb)</option>
                <option value="kg">Kilograms (kg)</option>
              </select>
            </label>
          </div>

          <label className="field">
            <span>Weight source</span>
            <input
              type="text"
              maxLength={512}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="Manufacturer specification or owner's manual"
              disabled={busy}
            />
          </label>

          <p className="m9-mass-help">
            Use the published curb weight for your exact configuration. The
            entry is recorded as user-provided, not independently
            manufacturer-verified. Supplying mass does not guarantee that
            terrain adjustment is available for every route.
          </p>

          <div className="m9-mass-actions">
            <button type="submit" className="v2-primary-button" disabled={busy}>
              {saving ? "Saving..." : "Save vehicle weight"}
            </button>

            <button
              type="button"
              className="v2-secondary-button"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {notice && (
        <p role="status" className="m9-mass-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="m9-mass-error">
          {error}
        </p>
      )}
    </div>
  );
}
