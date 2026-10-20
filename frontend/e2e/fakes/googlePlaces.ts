export interface PlaceSuggestion {
  id: string;
  primaryText: string;
  secondaryText: string | null;
}

export interface ResolvedE2ELocation {
  display_name: string;
  latitude: number;
  longitude: number;
  source: string;
  source_id: string;
}

export interface PlacesAutocompleteSession {
  fetchSuggestions(input: string): Promise<PlaceSuggestion[]>;
  resolveSuggestion(id: string): Promise<ResolvedE2ELocation>;
}

const locations: Record<string, ResolvedE2ELocation> = {
  "e2e-raleigh": {
    display_name: "Raleigh, NC",
    latitude: 35.7796,
    longitude: -78.6382,
    source: "google_places",
    source_id: "e2e-raleigh",
  },
  "e2e-ucsd": {
    display_name: "UC San Diego, La Jolla, CA",
    latitude: 32.8801,
    longitude: -117.234,
    source: "google_places",
    source_id: "e2e-ucsd",
  },

  "e2e-balboa": {
    display_name: "Balboa Park, San Diego, CA",
    latitude: 32.7341,
    longitude: -117.1446,
    source: "google_places",
    source_id: "e2e-balboa",
  },
};

export async function createPlacesAutocompleteSession(): Promise<PlacesAutocompleteSession> {
  return {
    async fetchSuggestions(input: string): Promise<PlaceSuggestion[]> {
      const normalizedInput = input.trim().toLowerCase();
      if (normalizedInput.includes("raleigh"))
        return [
          { id: "e2e-raleigh", primaryText: "Raleigh", secondaryText: "NC" },
        ];

      if (normalizedInput.includes("uc san")) {
        return [
          {
            id: "e2e-ucsd",
            primaryText: "UC San Diego",
            secondaryText: "La Jolla, CA",
          },
        ];
      }

      if (normalizedInput.includes("balboa")) {
        return [
          {
            id: "e2e-balboa",
            primaryText: "Balboa Park",
            secondaryText: "San Diego, CA",
          },
        ];
      }

      return [];
    },

    async resolveSuggestion(id: string): Promise<ResolvedE2ELocation> {
      const location = locations[id];

      if (location === undefined) {
        throw new Error("Unknown E2E place");
      }

      return location;
    },
  };
}
