import { beforeEach, describe, expect, it, vi } from "vitest";

import { updateSavedVehicleMass } from "./v2Resources";

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

const VEHICLE_ID = "11111111-1111-4111-8111-111111111111";

beforeEach(() => {
  vi.clearAllMocks();
  getJWTTokenMock.mockResolvedValue("valid-jwt");
});

describe("authenticated vehicle mass client", () => {
  it("sends decimal weight as a string with a bearer token", async () => {
    requestMock.mockResolvedValue({ id: VEHICLE_ID });

    await updateSavedVehicleMass(VEHICLE_ID, {
      weight: "3900.125",
      unit: "lb",
      source_reference: "Owner's manual",
    });

    expect(requestMock).toHaveBeenCalledWith(`/vehicles/${VEHICLE_ID}/mass`, {
      token: "valid-jwt",
      method: "PATCH",
      body: {
        weight: "3900.125",
        unit: "lb",
        source_reference: "Owner's manual",
      },
    });
  });

  it("allows clearing mass", async () => {
    requestMock.mockResolvedValue({ id: VEHICLE_ID });

    await updateSavedVehicleMass(VEHICLE_ID, { weight: null });

    expect(requestMock).toHaveBeenCalledWith(`/vehicles/${VEHICLE_ID}/mass`, {
      token: "valid-jwt",
      method: "PATCH",
      body: { weight: null },
    });
  });

  it("rejects an invalid vehicle identifier", async () => {
    await expect(
      updateSavedVehicleMass("../../other-user", { weight: null }),
    ).rejects.toThrow("Invalid saved vehicle ID.");

    expect(requestMock).not.toHaveBeenCalled();
  });

  it("does not make an unauthenticated request", async () => {
    getJWTTokenMock.mockResolvedValue(null);

    await expect(
      updateSavedVehicleMass(VEHICLE_ID, { weight: null }),
    ).rejects.toMatchObject({
      status: 401,
    });

    expect(requestMock).not.toHaveBeenCalled();
  });
});
