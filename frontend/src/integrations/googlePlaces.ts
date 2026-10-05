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

      const displayName =
        name && address ? `${name}, ${address}` : name || address;

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
