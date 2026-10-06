import { importLibrary, setOptions } from "@googlemaps/js-api-loader";

let googleMapsConfigured = false;

let placesLibraryPromise: Promise<google.maps.PlacesLibrary> | null = null;
let mapsLibraryPromise: Promise<google.maps.MapsLibrary> | null = null;
let coreLibraryPromise: Promise<google.maps.CoreLibrary> | null = null;

function getGoogleMapsApiKey(): string {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.trim();

  if (!apiKey) {
    throw new Error("VITE_GOOGLE_MAPS_API_KEY must be configured");
  }

  return apiKey;
}

function configureGoogleMaps(): void {
  if (googleMapsConfigured) {
    return;
  }

  setOptions({
    key: getGoogleMapsApiKey(),
  });

  googleMapsConfigured = true;
}

function loadRetryableLibrary<T>(
  libraryName: "places" | "maps" | "core",
  currentPromise: Promise<T> | null,
  setCurrentPromise: (promise: Promise<T> | null) => void,
): Promise<T> {
  if (currentPromise !== null) {
    return currentPromise;
  }

  const libraryPromise = importLibrary(libraryName) as Promise<T>;

  setCurrentPromise(libraryPromise);

  void libraryPromise.catch(() => {
    setCurrentPromise(null);
  });

  return libraryPromise;
}

export async function loadPlacesLibrary(): Promise<google.maps.PlacesLibrary> {
  configureGoogleMaps();

  return loadRetryableLibrary("places", placesLibraryPromise, (promise) => {
    placesLibraryPromise = promise;
  });
}

export async function loadMapsLibrary(): Promise<google.maps.MapsLibrary> {
  configureGoogleMaps();

  return loadRetryableLibrary("maps", mapsLibraryPromise, (promise) => {
    mapsLibraryPromise = promise;
  });
}

export async function loadCoreLibrary(): Promise<google.maps.CoreLibrary> {
  configureGoogleMaps();

  return loadRetryableLibrary("core", coreLibraryPromise, (promise) => {
    coreLibraryPromise = promise;
  });
}
