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

const suggestions = [
  {
    id: "place-id",
    primaryText: "UC San Diego",
    secondaryText: "La Jolla, CA",
  },
];

beforeEach(() => {
  vi.clearAllMocks();

  createPlacesAutocompleteSessionMock.mockResolvedValue({
    fetchSuggestions: fetchSuggestionsMock,
    resolveSuggestion: resolveSuggestionMock,
  });

  fetchSuggestionsMock.mockResolvedValue(suggestions);
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

  it("shows a clear empty state when no places match", async () => {
    fetchSuggestionsMock.mockResolvedValueOnce([]);

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
          value: "No matching place",
        },
      },
    );

    expect(
      await screen.findByText("No matching places found."),
    ).toBeInTheDocument();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("retries session creation after the Google Places session initially fails", async () => {
    createPlacesAutocompleteSessionMock
      .mockRejectedValueOnce(new Error("Google Places failed to load"))
      .mockResolvedValueOnce({
        fetchSuggestions: fetchSuggestionsMock,
        resolveSuggestion: resolveSuggestionMock,
      });

    render(
      <PlaceAutocompleteInput
        label="Origin"
        placeholder="Search origin"
        onLocationChange={vi.fn()}
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

    expect(
      await screen.findByText(
        "Unable to load place suggestions. Please try again.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(input, {
      target: {
        value: "UC San D",
      },
    });

    expect(await screen.findByText("UC San Diego")).toBeInTheDocument();

    expect(createPlacesAutocompleteSessionMock).toHaveBeenCalledTimes(2);
  });

  it("retries a failed suggestion request without recreating the session", async () => {
    fetchSuggestionsMock
      .mockRejectedValueOnce(new Error("temporary suggestion failure"))
      .mockResolvedValueOnce(suggestions);

    render(
      <PlaceAutocompleteInput
        label="Origin"
        placeholder="Search origin"
        onLocationChange={vi.fn()}
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

    expect(
      await screen.findByText(
        "Unable to load place suggestions. Please try again.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(input, {
      target: {
        value: "UC San D",
      },
    });

    expect(await screen.findByText("UC San Diego")).toBeInTheDocument();

    expect(createPlacesAutocompleteSessionMock).toHaveBeenCalledTimes(1);
    expect(fetchSuggestionsMock).toHaveBeenCalledTimes(2);
  });

  it("allows the user to retry after place resolution fails", async () => {
    const onLocationChange = vi.fn();

    resolveSuggestionMock
      .mockRejectedValueOnce(new Error("temporary resolution failure"))
      .mockResolvedValueOnce(resolvedLocation);

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

    const suggestionButton = screen.getByRole("button", {
      name: /UC San Diego/i,
    });

    fireEvent.click(suggestionButton);

    expect(
      await screen.findByText(
        "Unable to resolve the selected place. Please try again.",
      ),
    ).toBeInTheDocument();

    expect(onLocationChange).not.toHaveBeenCalled();

    fireEvent.click(suggestionButton);

    await waitFor(() => {
      expect(onLocationChange).toHaveBeenCalledWith(resolvedLocation);
    });

    expect(resolveSuggestionMock).toHaveBeenCalledTimes(2);
    expect(input).toHaveValue(resolvedLocation.display_name);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
