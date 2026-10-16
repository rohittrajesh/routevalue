import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getVehicleConfigurations,
  getVehicleMakes,
  getVehicleModels,
  getVehicleYears,
} from "./vehicleCatalog";

const { tokenMock, requestMock } = vi.hoisted(() => ({
  tokenMock: vi.fn(),
  requestMock: vi.fn(),
}));

vi.mock("./v2Resources", () => ({
  getAuthenticatedToken: tokenMock,
}));

vi.mock("./authenticatedClient", () => ({
  authenticatedV2Request: requestMock,
}));

beforeEach(() => {
  vi.clearAllMocks();
  tokenMock.mockResolvedValue("valid-jwt");
});

describe("vehicle catalog HTTP client", () => {
  it("retrieves available years", async () => {
    requestMock.mockResolvedValue({
      years: [2026, 2025],
    });

    await expect(getVehicleYears()).resolves.toEqual([2026, 2025]);

    expect(requestMock).toHaveBeenCalledWith("/vehicle-catalog/years", {
      token: "valid-jwt",
      method: "GET",
    });
  });

  it("retrieves makes for a selected year", async () => {
    requestMock.mockResolvedValue({
      makes: ["Honda", "Toyota"],
    });

    await expect(getVehicleMakes(2026)).resolves.toEqual(["Honda", "Toyota"]);

    expect(requestMock).toHaveBeenCalledWith(
      "/vehicle-catalog/makes?year=2026",
      {
        token: "valid-jwt",
        method: "GET",
      },
    );
  });

  it("encodes special characters in a selected make", async () => {
    requestMock.mockResolvedValue({
      models: ["Example"],
    });

    await getVehicleModels(2026, "Ram & Dodge");

    expect(requestMock).toHaveBeenCalledWith(
      "/vehicle-catalog/models?year=2026&make=Ram+%26+Dodge",
      {
        token: "valid-jwt",
        method: "GET",
      },
    );
  });

  it("retrieves configurations with provenance", async () => {
    const configuration = {
      year: 2026,
      make: "Toyota",
      model: "Camry",
      configuration: "2.5L 4cyl CVT (FWD)",
      source: "fueleconomy_gov",
      source_id: "12345",
    };

    requestMock.mockResolvedValue({
      configurations: [configuration],
    });

    await expect(
      getVehicleConfigurations(2026, "Toyota", "Camry"),
    ).resolves.toEqual([configuration]);

    expect(requestMock).toHaveBeenCalledWith(
      "/vehicle-catalog/configurations?year=2026&make=Toyota&model=Camry",
      {
        token: "valid-jwt",
        method: "GET",
      },
    );
  });

  it("does not request a catalog without a token", async () => {
    tokenMock.mockRejectedValue(new Error("Authentication required"));

    await expect(getVehicleYears()).rejects.toThrow("Authentication required");

    expect(requestMock).not.toHaveBeenCalled();
  });
});
