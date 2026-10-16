import { useEffect, useState, type FormEvent } from "react";

import {
  getVehicleConfigurations,
  getVehicleMakes,
  getVehicleModels,
  getVehicleYears,
  type VehicleCatalogConfiguration,
} from "../api/vehicleCatalog";

interface VehicleCatalogPickerProps {
  onSave: (configuration: VehicleCatalogConfiguration) => Promise<boolean>;
  disabled?: boolean;
}

type LoadStatus = "loading" | "ready" | "error";

interface OptionState<T> {
  status: LoadStatus;
  options: T[];
}

export default function VehicleCatalogPicker({
  onSave,
  disabled = false,
}: VehicleCatalogPickerProps) {
  const [years, setYears] = useState<OptionState<number>>({
    status: "loading",
    options: [],
  });
  const [makes, setMakes] = useState<OptionState<string>>({
    status: "ready",
    options: [],
  });
  const [models, setModels] = useState<OptionState<string>>({
    status: "ready",
    options: [],
  });
  const [configurations, setConfigurations] = useState<
    OptionState<VehicleCatalogConfiguration>
  >({
    status: "ready",
    options: [],
  });

  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [retryVersion, setRetryVersion] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;

    void getVehicleYears().then(
      (options) => {
        if (active) {
          setYears({ status: "ready", options });
        }
      },
      () => {
        if (active) {
          setYears({ status: "error", options: [] });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [retryVersion]);

  useEffect(() => {
    if (!year) {
      return;
    }

    let active = true;

    void getVehicleMakes(Number(year)).then(
      (options) => {
        if (active) {
          setMakes({ status: "ready", options });
        }
      },
      () => {
        if (active) {
          setMakes({ status: "error", options: [] });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [year, retryVersion]);

  useEffect(() => {
    if (!year || !make) {
      return;
    }

    let active = true;

    void getVehicleModels(Number(year), make).then(
      (options) => {
        if (active) {
          setModels({ status: "ready", options });
        }
      },
      () => {
        if (active) {
          setModels({ status: "error", options: [] });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [year, make, retryVersion]);

  useEffect(() => {
    if (!year || !make || !model) {
      return;
    }

    let active = true;

    void getVehicleConfigurations(Number(year), make, model).then(
      (options) => {
        if (active) {
          setConfigurations({ status: "ready", options });
        }
      },
      () => {
        if (active) {
          setConfigurations({ status: "error", options: [] });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [year, make, model, retryVersion]);

  function changeYear(next: string) {
    setYear(next);
    setMake("");
    setModel("");
    setSourceId("");

    setMakes({
      status: next ? "loading" : "ready",
      options: [],
    });
    setModels({ status: "ready", options: [] });
    setConfigurations({ status: "ready", options: [] });
  }

  function changeMake(next: string) {
    setMake(next);
    setModel("");
    setSourceId("");

    setModels({
      status: next ? "loading" : "ready",
      options: [],
    });
    setConfigurations({ status: "ready", options: [] });
  }

  function changeModel(next: string) {
    setModel(next);
    setSourceId("");

    setConfigurations({
      status: next ? "loading" : "ready",
      options: [],
    });
  }

  function retryCatalog() {
    if (years.status === "error") {
      setYears({ status: "loading", options: [] });
    }

    if (makes.status === "error") {
      setMakes({ status: "loading", options: [] });
    }

    if (models.status === "error") {
      setModels({ status: "loading", options: [] });
    }

    if (configurations.status === "error") {
      setConfigurations({ status: "loading", options: [] });
    }

    setRetryVersion((current) => current + 1);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const selected = configurations.options.find(
      (option) => option.source_id === sourceId,
    );

    if (!selected || saving || disabled) {
      return;
    }

    setSaving(true);

    try {
      const saved = await onSave(selected);

      if (saved) {
        setSourceId("");
      }
    } finally {
      setSaving(false);
    }
  }

  const loading =
    years.status === "loading" ||
    makes.status === "loading" ||
    models.status === "loading" ||
    configurations.status === "loading";

  const failed =
    years.status === "error" ||
    makes.status === "error" ||
    models.status === "error" ||
    configurations.status === "error";

  return (
    <form
      className="m9-catalog-form"
      onSubmit={(event) => void handleSave(event)}
    >
      <div className="m9-field-grid">
        <label className="field">
          <span>Model year</span>
          <select
            value={year}
            onChange={(event) => changeYear(event.target.value)}
            disabled={disabled || saving || years.status !== "ready"}
            required
          >
            <option value="">Select year</option>
            {years.options.map((option) => (
              <option key={option} value={String(option)}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Make</span>
          <select
            value={make}
            onChange={(event) => changeMake(event.target.value)}
            disabled={disabled || saving || !year || makes.status !== "ready"}
            required
          >
            <option value="">Select make</option>
            {makes.options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Model</span>
          <select
            value={model}
            onChange={(event) => changeModel(event.target.value)}
            disabled={disabled || saving || !make || models.status !== "ready"}
            required
          >
            <option value="">Select model</option>
            {models.options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Configuration</span>
          <select
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            disabled={
              disabled || saving || !model || configurations.status !== "ready"
            }
            required
          >
            <option value="">Select configuration</option>
            {configurations.options.map((option) => (
              <option key={option.source_id} value={option.source_id}>
                {option.configuration}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <p role="status" className="m9-note">
          Loading vehicle options...
        </p>
      )}

      {failed && (
        <div className="m9-feedback m9-error">
          <p role="alert">Could not load vehicle options.</p>
          <button
            type="button"
            className="v2-secondary-button"
            onClick={retryCatalog}
            disabled={disabled || saving}
          >
            Retry catalog
          </button>
        </div>
      )}

      <button
        type="submit"
        className="v2-primary-button"
        disabled={disabled || saving || loading || !sourceId}
      >
        {saving ? "Saving vehicle..." : "Save vehicle"}
      </button>

      <p className="m9-note">
        Vehicle efficiency is retrieved and verified by the RouteValue backend.
        You cannot override these specifications.
      </p>
    </form>
  );
}
