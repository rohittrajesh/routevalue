import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlaceSuggestion } from "./googlePlaces";

const { loadPlacesLibraryMock } = vi.hoisted(() => ({
  loadPlacesLibraryMock: vi.fn(),
}));

vi.mock("./googleMaps", () => ({
  loadPlacesLibrary: loadPlacesLibraryMock,
}));

interface FakePlaceState {
  id?: string;
  displayName?: string;
  formattedAddress?: string;
  latitude?: number;
  longitude?: number;
}

interface BuildPredictionOptions {
  placeId: string;
  primaryText: string;
  secondaryText: string | null;
  place: google.maps.places.Place;
}

function buildFakePlace(state: FakePlaceState): google.maps.places.Place {
  const fetchFields = vi.fn().mockResolvedValue(undefined);

  return {
    id: state.id,
    displayName: state.displayName,
    formattedAddress: state.formattedAddress,
    location:
      state.latitude !== undefined && state.longitude !== undefined
        ? {
            lat: () => state.latitude!,
            lng: () => state.longitude!,
          }
        : undefined,
    fetchFields,
  } as unknown as google.maps.places.Place;
}

function buildPrediction({
  placeId,
  primaryText,
  secondaryText,
  place,
}: BuildPredictionOptions): google.maps.places.PlacePrediction {
  return {
    placeId,
    mainText: {
      text: primaryText,
    },
    secondaryText:
      secondaryText === null
        ? undefined
        : {
            text: secondaryText,
          },
    text: {
      text:
        secondaryText === null
          ? primaryText
          : `${primaryText}, ${secondaryText}`,
    },
    toPlace: () => place,
  } as unknown as google.maps.places.PlacePrediction;
}

function configurePlacesLibrary(
  predictions: google.maps.places.PlacePrediction[],
) {
  class FakeAutocompleteSessionToken {}

  const fetchAutocompleteSuggestions = vi.fn().mockResolvedValue({
    suggestions: predictions.map((prediction) => ({
      placePrediction: prediction,
    })),
  });

  loadPlacesLibraryMock.mockResolvedValue({
    AutocompleteSessionToken: FakeAutocompleteSessionToken,
    AutocompleteSuggestion: {
      fetchAutocompleteSuggestions,
    },
  } as unknown as google.maps.PlacesLibrary);

  return {
    fetchAutocompleteSuggestions,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("createPlacesAutocompleteSession", () => {
  it("returns no suggestions for blank input", async () => {
    const { fetchAutocompleteSuggestions } = configurePlacesLibrary([]);

    const { createPlacesAutocompleteSession } = await import("./googlePlaces");

    const session = await createPlacesAutocompleteSession();

    await expect(session.fetchSuggestions("   ")).resolves.toEqual([]);

    expect(fetchAutocompleteSuggestions).not.toHaveBeenCalled();
  });

  it("normalizes Google place predictions", async () => {
    const place = buildFakePlace({
      id: "place-id",
      displayName: "UC San Diego",
      formattedAddress: "9500 Gilman Dr, La Jolla, CA 92093",
      latitude: 32.8801,
      longitude: -117.234,
    });

    const prediction = buildPrediction({
      placeId: "place-id",
      primaryText: "UC San Diego",
      secondaryText: "La Jolla, CA",
      place,
    });

    configurePlacesLibrary([prediction]);

    const { createPlacesAutocompleteSession } = await import("./googlePlaces");

    const session = await createPlacesAutocompleteSession();

    const suggestions = await session.fetchSuggestions("UC San");

    const expected: PlaceSuggestion[] = [
      {
        id: "place-id",
        primaryText: "UC San Diego",
        secondaryText: "La Jolla, CA",
      },
    ];

    expect(suggestions).toEqual(expected);
  });

  it("resolves a selected prediction into a RouteValue location", async () => {
    const place = buildFakePlace({
      id: "place-id",
      displayName: "UC San Diego",
      formattedAddress: "9500 Gilman Dr, La Jolla, CA 92093",
      latitude: 32.8801,
      longitude: -117.234,
    });

    const prediction = buildPrediction({
      placeId: "place-id",
      primaryText: "UC San Diego",
      secondaryText: "La Jolla, CA",
      place,
    });

    configurePlacesLibrary([prediction]);

    const { createPlacesAutocompleteSession } = await import("./googlePlaces");

    const session = await createPlacesAutocompleteSession();

    await session.fetchSuggestions("UC San");

    await expect(session.resolveSuggestion("place-id")).resolves.toEqual({
      display_name: "UC San Diego, 9500 Gilman Dr, La Jolla, CA 92093",
      latitude: 32.8801,
      longitude: -117.234,
      source: "google_places",
      source_id: "place-id",
    });

    expect(place.fetchFields).toHaveBeenCalledWith({
      fields: ["id", "displayName", "formattedAddress", "location"],
    });
  });

  it("rejects a suggestion that is no longer available", async () => {
    configurePlacesLibrary([]);

    const { createPlacesAutocompleteSession } = await import("./googlePlaces");

    const session = await createPlacesAutocompleteSession();

    await expect(session.resolveSuggestion("missing-place-id")).rejects.toThrow(
      "Selected place suggestion is no longer available",
    );
  });
});
