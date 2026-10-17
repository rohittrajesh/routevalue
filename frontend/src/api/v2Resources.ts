
import type { components } from "./generated/schema";
import type {
  V2TripEvaluationRequest,
  V2TripEvaluationResponse,
} from "../types/api";

import { getNeonAuthClient } from "../auth/neonClient";
import { authenticatedV2Request } from "./authenticatedClient";
import { ApiRequestError } from "./tripEvaluations";

type Schemas = components["schemas"];

export type UserProfile = Schemas["UserProfileResponse"];
export type UserPreferences = Schemas["UserPreferencesResponse"];
export type PreferencesUpdate = Schemas["UserPreferencesUpdateRequest"];
export type SavedVehicle = Schemas["SavedVehicleResponse"];
export type SavedVehicleCreate = Schemas["SavedVehicleCreateRequest"];
export type SavedVehicleList = Schemas["SavedVehicleListResponse"];
export type VehicleMassUpdate = Schemas["VehicleMassUpdateRequest"];

const VEHICLE_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function getAuthenticatedToken(): Promise<string> {
  const auth = getNeonAuthClient();

  let token: string | null;

  try {
    token = await auth.getJWTToken();
  } catch {
    throw new ApiRequestError(
      "Could not verify your session. Please try again.",
      null,
      "network_error",
    );
  }

  if (token === null || !token.trim() || token.trim() !== token) {
    throw new ApiRequestError(
      "Please sign in to continue.",
      401,
      "authentication_required",
    );
  }

  return token;
}

async function requestV2<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE" = "GET",
  body?: unknown,
): Promise<T> {
  const token = await getAuthenticatedToken();

  return authenticatedV2Request<T>(path, {
    token,
    method,
    body,
  });
}

export async function getCurrentProfile(): Promise<UserProfile> {
  return requestV2<UserProfile>("/me");
}

export async function getUserPreferences(): Promise<UserPreferences> {
  return requestV2<UserPreferences>("/preferences");
}

export async function updateUserPreferences(
  changes: PreferencesUpdate,
): Promise<UserPreferences> {
  return requestV2<UserPreferences>("/preferences", "PATCH", changes);
}

export async function getSavedVehicles(): Promise<SavedVehicleList> {
  return requestV2<SavedVehicleList>("/vehicles");
}

export async function createSavedVehicle(
  selection: SavedVehicleCreate,
): Promise<SavedVehicle> {
  return requestV2<SavedVehicle>("/vehicles", "POST", selection);
}

export async function deleteSavedVehicle(vehicleId: string): Promise<void> {
  if (!VEHICLE_ID_PATTERN.test(vehicleId)) {
    throw new Error("Invalid saved vehicle ID.");
  }

  return requestV2<void>(`/vehicles/${vehicleId}`, "DELETE");
}

export async function updateSavedVehicleMass(
  vehicleId: string,
  changes: VehicleMassUpdate,
): Promise<SavedVehicle> {
  if (!VEHICLE_ID_PATTERN.test(vehicleId)) {
    throw new Error("Invalid saved vehicle ID.");
  }

  return requestV2<SavedVehicle>(
    `/vehicles/${vehicleId}/mass`,
    "PATCH",
    changes,
  );
}

export async function evaluateV2Trip(
  request: V2TripEvaluationRequest,
): Promise<V2TripEvaluationResponse> {
  return requestV2<V2TripEvaluationResponse>(
    "/trip-evaluations",
    "POST",
    request,
  );
}
