import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PlaceAutocompleteInput from "./PlaceAutocompleteInput";

const {
  createPlacesAutocompleteSessionMock,
  fetchSuggestionsMock,
  resolveSuggestionMock,
} = vi.hoisted(() => ({
  createPlacesAutocompleteSessionMock: vi.fn(),
  fetchSuggestionsMock: vi.fn(),
  resolveSuggestionMock: vi.fn(),
}));

vi.mock("../integrations/googlePlaces", () => ({
  createPlacesAutocompleteSession: createPlacesAutocompleteSessionMock,
}));

const resolvedLocation = {
  display_name: "UC San Diego, 9500 Gilman Dr, La Jolla, CA 92093",
  latitude: 32.8801,
  longitude: -117.234,
  source: "google_places",
  source_id: "place-id",
};

beforeEach(() => {
  vi.clearAllMocks();

  createPlacesAutocompleteSessionMock.mockResolvedValue({
    fetchSuggestions: fetchSuggestionsMock,
    resolveSuggestion: resolveSuggestionMock,
  });

  fetchSuggestionsMock.mockResolvedValue([
    {
      id: "place-id",
      primaryText: "UC San Diego",
      secondaryText: "La Jolla, CA",
    },
  ]);

  resolveSuggestionMock.mockResolvedValue(resolvedLocation);
});

describe("PlaceAutocompleteInput", () => {
  it("shows suggestions after the user types", async () => {
    render(
      <PlaceAutocompleteInput
        label="Origin"
        placeholder="Search origin"
        onLocationChange={vi.fn()}
      />,
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Origin",
      }),
      {
        target: {
          value: "UC San",
        },
      },
    );

    await waitFor(() => {
      expect(fetchSuggestionsMock).toHaveBeenCalledWith("UC San");
    });

    expect(await screen.findByText("UC San Diego")).toBeInTheDocument();

    expect(screen.getByText("La Jolla, CA")).toBeInTheDocument();
  });

  it("selects the active suggestion with Enter", async () => {
    const onLocationChange = vi.fn();

    render(
      <PlaceAutocompleteInput
        label="Origin"
        placeholder="Search origin"
        onLocationChange={onLocationChange}
      />,
    );

    const input = screen.getByRole("combobox", {
      name: "Origin",
    });

    fireEvent.change(input, {
      target: {
        value: "UC San",
      },
    });

    await waitFor(() => {
      expect(fetchSuggestionsMock).toHaveBeenCalled();
    });

    await screen.findByText("UC San Diego");

    fireEvent.keyDown(input, {
      key: "Enter",
    });

    await waitFor(() => {
      expect(resolveSuggestionMock).toHaveBeenCalledWith("place-id");
    });

    expect(onLocationChange).toHaveBeenCalledWith(resolvedLocation);

    expect(input).toHaveValue(resolvedLocation.display_name);
  });

  it("invalidates a selected place when the user edits it", async () => {
    const onLocationChange = vi.fn();

    render(
      <PlaceAutocompleteInput
        label="Origin"
        placeholder="Search origin"
        onLocationChange={onLocationChange}
      />,
    );

    const input = screen.getByRole("combobox", {
      name: "Origin",
    });

    fireEvent.change(input, {
      target: {
        value: "UC San",
      },
    });

    await screen.findByText("UC San Diego");

    fireEvent.click(
      screen.getByRole("button", {
        name: /UC San Diego/i,
      }),
    );

    await waitFor(() => {
      expect(onLocationChange).toHaveBeenCalledWith(resolvedLocation);
    });

    fireEvent.change(input, {
      target: {
        value: "UC San Diego edited",
      },
    });

    expect(onLocationChange).toHaveBeenLastCalledWith(null);
  });
});
