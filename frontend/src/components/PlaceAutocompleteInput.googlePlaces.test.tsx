import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import PlaceAutocompleteInput from "./PlaceAutocompleteInput";

const { loadPlacesLibraryMock } = vi.hoisted(() => ({
  loadPlacesLibraryMock: vi.fn(),
}));
vi.mock("../integrations/googleMaps", () => ({
  loadPlacesLibrary: loadPlacesLibraryMock,
}));

const address = "123 Example Lane, Example City, CA 90000, USA";

beforeEach(() => {
  vi.clearAllMocks();
  class SessionToken {}
  const place = {
    id: "synthetic-address-id",
    displayName: "123 Example Lane",
    formattedAddress: address,
    location: { lat: () => 34.05, lng: () => -118.25 },
    fetchFields: vi.fn().mockResolvedValue(undefined),
  };
  loadPlacesLibraryMock.mockResolvedValue({
    AutocompleteSessionToken: SessionToken,
    AutocompleteSuggestion: {
      fetchAutocompleteSuggestions: vi.fn().mockResolvedValue({
        suggestions: [
          {
            placePrediction: {
              placeId: place.id,
              mainText: { text: "123 Example Lane" },
              secondaryText: { text: "Example City, CA" },
              text: { text: address },
              toPlace: () => place,
            },
          },
        ],
      }),
    },
  } as unknown as google.maps.PlacesLibrary);
});

// Exercise the real Places adapter together with the controlled input. Only the
// external SDK is replaced; bypassing the adapter would miss the duplicate label.
it.each([
  { label: "Origin", keyboard: false },
  { label: "Destination", keyboard: true },
  { label: "Fuel purchasing area", keyboard: false },
])(
  "replaces partial $label text with one resolved address",
  async ({ label, keyboard }) => {
    const onLocationChange = vi.fn();
    render(
      <PlaceAutocompleteInput
        label={label}
        placeholder="Choose a location"
        onLocationChange={onLocationChange}
      />,
    );
    const input = screen.getByRole("combobox", { name: label });
    fireEvent.change(input, { target: { value: "123 Ex" } });
    const suggestion = await screen.findByRole("button", {
      name: /123 Example Lane/,
    });
    if (keyboard) fireEvent.keyDown(input, { key: "Enter" });
    else fireEvent.click(suggestion);
    await waitFor(() => expect(input).toHaveValue(address));
    expect(onLocationChange).toHaveBeenLastCalledWith({
      display_name: address,
      latitude: 34.05,
      longitude: -118.25,
      source: "google_places",
      source_id: "synthetic-address-id",
    });
    expect(screen.getByLabelText("Resolved location selected")).toBeVisible();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  },
);
