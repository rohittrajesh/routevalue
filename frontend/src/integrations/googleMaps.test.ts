import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { importLibraryMock, setOptionsMock } = vi.hoisted(() => ({
  importLibraryMock: vi.fn(),
  setOptionsMock: vi.fn(),
}));

vi.mock("@googlemaps/js-api-loader", () => ({
  importLibrary: importLibraryMock,
  setOptions: setOptionsMock,
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("loadPlacesLibrary", () => {
  it("requires a Google Maps browser API key", async () => {
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "");

    const { loadPlacesLibrary } = await import("./googleMaps");

    await expect(loadPlacesLibrary()).rejects.toThrow(
      "VITE_GOOGLE_MAPS_API_KEY must be configured",
    );

    expect(setOptionsMock).not.toHaveBeenCalled();
    expect(importLibraryMock).not.toHaveBeenCalled();
  });

  it("loads the Places library with the configured key", async () => {
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "test-browser-key");

    const placesLibrary = {} as google.maps.PlacesLibrary;

    importLibraryMock.mockResolvedValue(placesLibrary);

    const { loadPlacesLibrary } = await import("./googleMaps");

    await expect(loadPlacesLibrary()).resolves.toBe(placesLibrary);

    expect(setOptionsMock).toHaveBeenCalledWith({
      key: "test-browser-key",
    });
    expect(importLibraryMock).toHaveBeenCalledWith("places");
  });

  it("loads the Places library only once", async () => {
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "test-browser-key");

    const placesLibrary = {} as google.maps.PlacesLibrary;

    importLibraryMock.mockResolvedValue(placesLibrary);

    const { loadPlacesLibrary } = await import("./googleMaps");

    await loadPlacesLibrary();
    await loadPlacesLibrary();

    expect(setOptionsMock).toHaveBeenCalledTimes(1);
    expect(importLibraryMock).toHaveBeenCalledTimes(1);
  });
});
