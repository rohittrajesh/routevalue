import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  evaluateV2Trip,
  getAuthenticatedToken,
  getCurrentProfile,
  getSavedVehicles,
  updateUserPreferences,
} from "./v2Resources";

const { getJWTTokenMock, requestMock } = vi.hoisted(() => ({
  getJWTTokenMock: vi.fn(),
  requestMock: vi.fn(),
}));

vi.mock("../auth/neonClient", () => ({
  getNeonAuthClient: () => ({
    getJWTToken: getJWTTokenMock,
  }),
}));

vi.mock("./authenticatedClient", () => ({
  authenticatedV2Request: requestMock,
}));

beforeEach(() => {
  vi.clearAllMocks();
  getJWTTokenMock.mockResolvedValue("valid-jwt");
});

describe("authenticated V2 resources", () => {
  it("obtains an authenticated JWT", async () => {
    await expect(getAuthenticatedToken()).resolves.toBe("valid-jwt");
  });

  it("rejects missing JWT credentials", async () => {
    getJWTTokenMock.mockResolvedValue(null);

    await expect(getCurrentProfile()).rejects.toMatchObject({
      status: 401,
      code: "authentication_required",
    });

    expect(requestMock).not.toHaveBeenCalled();
  });

  it("requests the current profile", async () => {
    const profile = {
      user_id: "user-123",
      default_vehicle_id: null,
      preferences_configured: false,
    };

    requestMock.mockResolvedValue(profile);

    await expect(getCurrentProfile()).resolves.toEqual(profile);

    expect(requestMock).toHaveBeenCalledWith("/me", {
      token: "valid-jwt",
      method: "GET",
      body: undefined,
    });
  });

  it("updates persisted preferences", async () => {
    requestMock.mockResolvedValue({
      value_of_time_per_hour: "25.00",
      default_vehicle_id: null,
    });

    await updateUserPreferences({
      value_of_time_per_hour: "25.00",
    });

    expect(requestMock).toHaveBeenCalledWith("/preferences", {
      token: "valid-jwt",
      method: "PATCH",
      body: {
        value_of_time_per_hour: "25.00",
      },
    });
  });

  it("requests saved vehicles", async () => {
    requestMock.mockResolvedValue({ vehicles: [] });

    await expect(getSavedVehicles()).resolves.toEqual({
      vehicles: [],
    });
  });

  it("sends a profile-driven V2 trip", async () => {
    const trip = {
      origin: {
        display_name: "Origin",
        latitude: 32.88,
        longitude: -117.23,
        source: "google_places" as const,
        source_id: "origin-id",
      },
      destination: {
        display_name: "Destination",
        latitude: 32.89,
        longitude: -117.24,
        source: "google_places" as const,
        source_id: "destination-id",
      },
    };

    requestMock.mockResolvedValue({
      route_evaluations: [],
      decision: {},
    });

    await evaluateV2Trip(trip);

    expect(requestMock).toHaveBeenCalledWith("/trip-evaluations", {
      token: "valid-jwt",
      method: "POST",
      body: trip,
    });
  });
});
