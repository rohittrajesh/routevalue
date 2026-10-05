import { importLibrary, setOptions } from "@googlemaps/js-api-loader";

let placesLibraryPromise: Promise<google.maps.PlacesLibrary> | null = null;

function getGoogleMapsApiKey(): string {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.trim();

  if (!apiKey) {
    throw new Error("VITE_GOOGLE_MAPS_API_KEY must be configured");
  }

  return apiKey;
}

export async function loadPlacesLibrary(): Promise<google.maps.PlacesLibrary> {
  if (placesLibraryPromise === null) {
    setOptions({
      key: getGoogleMapsApiKey(),
    });

    placesLibraryPromise = importLibrary("places");
  }

  return placesLibraryPromise;
}
