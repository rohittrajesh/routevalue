import type { ResolvedLocationInput } from "../types/api";
import { loadPlacesLibrary } from "./googleMaps";

export interface PlaceSuggestion {
  id: string;
  primaryText: string;
  secondaryText: string | null;
}

export interface PlacesAutocompleteSession {
  fetchSuggestions(input: string): Promise<PlaceSuggestion[]>;
  resolveSuggestion(id: string): Promise<ResolvedLocationInput>;
}

function formatPlaceDisplayName(
  name: string | undefined,
  address: string | undefined,
): string | undefined {
  if (!name || !address) return name || address;

  // Google can use the street address itself as the place name. Compare whole
  // comma-delimited prefixes so a distinct business name is never dropped just
  // because it shares the first few characters of an address.
  const normalize = (value: string): string =>
    value
      .replace(/\s+/g, " ")
      .replace(/\s*,\s*/g, ",")
      .toLowerCase();
  const normalizedName = normalize(name);
  const normalizedAddress = normalize(address);
  if (
    normalizedAddress === normalizedName ||
    normalizedAddress.startsWith(`${normalizedName},`)
  ) {
    return address;
  }

  return `${name}, ${address}`;
}

export async function createPlacesAutocompleteSession(): Promise<PlacesAutocompleteSession> {
  const { AutocompleteSessionToken, AutocompleteSuggestion } =
    await loadPlacesLibrary();

  let sessionToken = new AutocompleteSessionToken();

  const predictions = new Map<string, google.maps.places.PlacePrediction>();

  function resetSession() {
    sessionToken = new AutocompleteSessionToken();
    predictions.clear();
  }

  return {
    async fetchSuggestions(input: string): Promise<PlaceSuggestion[]> {
      const normalizedInput = input.trim();

      if (!normalizedInput) {
        predictions.clear();
        return [];
      }

      const { suggestions } =
        await AutocompleteSuggestion.fetchAutocompleteSuggestions({
          input: normalizedInput,
          sessionToken,
        });

      predictions.clear();

      const results: PlaceSuggestion[] = [];

      for (const suggestion of suggestions) {
        const prediction = suggestion.placePrediction;

        if (!prediction) {
          continue;
        }

        predictions.set(prediction.placeId, prediction);

        results.push({
          id: prediction.placeId,
          primaryText: prediction.mainText?.text ?? prediction.text.text,
          secondaryText: prediction.secondaryText?.text ?? null,
        });
      }

      return results;
    },

    async resolveSuggestion(id: string): Promise<ResolvedLocationInput> {
      const prediction = predictions.get(id);

      if (!prediction) {
        throw new Error("Selected place suggestion is no longer available");
      }

      const place = prediction.toPlace();

      await place.fetchFields({
        fields: ["id", "displayName", "formattedAddress", "location"],
      });

      if (!place.id) {
        throw new Error("Selected place does not have a place identifier");
      }

      if (!place.location) {
        throw new Error("Selected place does not have routable coordinates");
      }

      const name = place.displayName?.trim();
      const address = place.formattedAddress?.trim();

      const displayName = formatPlaceDisplayName(name, address);

      if (!displayName) {
        throw new Error("Selected place does not have a display name");
      }

      const resolvedLocation: ResolvedLocationInput = {
        display_name: displayName,
        latitude: place.location.lat(),
        longitude: place.location.lng(),
        source: "google_places",
        source_id: place.id,
      };

      resetSession();

      return resolvedLocation;
    },
  };
}
