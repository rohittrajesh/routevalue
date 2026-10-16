import type { components } from "./generated/schema";

import { authenticatedV2Request } from "./authenticatedClient";
import { getAuthenticatedToken } from "./v2Resources";

type Schemas = components["schemas"];

export type VehicleCatalogConfiguration =
  Schemas["VehicleCatalogConfigurationResponse"];

type YearsResponse = Schemas["VehicleYearsResponse"];
type MakesResponse = Schemas["VehicleMakesResponse"];
type ModelsResponse = Schemas["VehicleModelsResponse"];
type ConfigurationsResponse = Schemas["VehicleConfigurationsResponse"];

async function requestCatalog<T>(path: string): Promise<T> {
  const token = await getAuthenticatedToken();

  return authenticatedV2Request<T>(`/vehicle-catalog/${path}`, {
    token,
    method: "GET",
  });
}

export async function getVehicleYears(): Promise<number[]> {
  const response = await requestCatalog<YearsResponse>("years");

  return response.years;
}

export async function getVehicleMakes(year: number): Promise<string[]> {
  const query = new URLSearchParams({
    year: String(year),
  });

  const response = await requestCatalog<MakesResponse>(
    `makes?${query.toString()}`,
  );

  return response.makes;
}

export async function getVehicleModels(
  year: number,
  make: string,
): Promise<string[]> {
  const query = new URLSearchParams({
    year: String(year),
    make,
  });

  const response = await requestCatalog<ModelsResponse>(
    `models?${query.toString()}`,
  );

  return response.models;
}

export async function getVehicleConfigurations(
  year: number,
  make: string,
  model: string,
): Promise<VehicleCatalogConfiguration[]> {
  const query = new URLSearchParams({
    year: String(year),
    make,
    model,
  });

  const response = await requestCatalog<ConfigurationsResponse>(
    `configurations?${query.toString()}`,
  );

  return response.configurations;
}
