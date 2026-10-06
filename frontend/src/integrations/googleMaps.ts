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

export async function loadPlacesLibrary(): Promise<google.maps.PlacesLibrary> {
  configureGoogleMaps();

  if (placesLibraryPromise === null) {
    placesLibraryPromise = importLibrary("places");
  }

  return placesLibraryPromise;
}

export async function loadMapsLibrary(): Promise<google.maps.MapsLibrary> {
  configureGoogleMaps();

  if (mapsLibraryPromise === null) {
    mapsLibraryPromise = importLibrary("maps");
  }

  return mapsLibraryPromise;
}

export async function loadCoreLibrary(): Promise<google.maps.CoreLibrary> {
  configureGoogleMaps();

  if (coreLibraryPromise === null) {
    coreLibraryPromise = importLibrary("core");
  }

  return coreLibraryPromise;
}
