import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResolvedLocationInput } from "../types/api";
import TripForm from "./TripForm";

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

const originLocation: ResolvedLocationInput = {
  display_name: "Origin Place, 100 Origin St, San Diego, CA",
  latitude: 32.88,
  longitude: -117.23,
  source: "google_places",
  source_id: "origin-place-id",
};

const destinationLocation: ResolvedLocationInput = {
  display_name: "Destination Place, 200 Destination St, San Diego, CA",
  latitude: 32.73,
  longitude: -117.19,
  source: "google_places",
  source_id: "destination-place-id",
};

beforeEach(() => {
  vi.clearAllMocks();

  fetchSuggestionsMock.mockImplementation(async (input: string) => {
    if (input.toLowerCase().includes("origin")) {
      return [
        {
          id: "origin-place-id",
          primaryText: "Origin Place",
          secondaryText: "San Diego, CA",
        },
      ];
    }

    return [
      {
        id: "destination-place-id",
        primaryText: "Destination Place",
        secondaryText: "San Diego, CA",
      },
    ];
  });

  resolveSuggestionMock.mockImplementation(async (id: string) => {
    if (id === "origin-place-id") {
      return originLocation;
    }

    if (id === "destination-place-id") {
      return destinationLocation;
    }

    throw new Error("Unknown place");
  });

  createPlacesAutocompleteSessionMock.mockResolvedValue({
    fetchSuggestions: fetchSuggestionsMock,
    resolveSuggestion: resolveSuggestionMock,
  });
});

async function selectOrigin() {
  const originInput = screen.getByRole("combobox", {
    name: "Origin",
  });

  fireEvent.change(originInput, {
    target: {
      value: "Origin",
    },
  });

  const suggestion = await screen.findByRole("button", {
    name: /Origin Place/i,
  });

  fireEvent.click(suggestion);

  await waitFor(() => {
    expect(originInput).toHaveValue(originLocation.display_name);
  });
}

async function selectDestination() {
  const destinationInput = screen.getByRole("combobox", {
    name: "Destination",
  });

  fireEvent.change(destinationInput, {
    target: {
      value: "Destination",
    },
  });

  const suggestion = await screen.findByRole("button", {
    name: /Destination Place/i,
  });

  fireEvent.click(suggestion);

  await waitFor(() => {
    expect(destinationInput).toHaveValue(destinationLocation.display_name);
  });
}

describe("TripForm", () => {
  it("does not allow submission when locations are only typed", async () => {
    const onSubmit = vi.fn();

    render(<TripForm onSubmit={onSubmit} isSubmitting={false} />);

    const compareButton = screen.getByRole("button", {
      name: "Compare routes",
    });

    expect(compareButton).toBeDisabled();

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Origin",
      }),
      {
        target: {
          value: "Typed origin",
        },
      },
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Destination",
      }),
      {
        target: {
          value: "Typed destination",
        },
      },
    );

    await waitFor(() => {
      expect(fetchSuggestionsMock).toHaveBeenCalled();
    });

    expect(compareButton).toBeDisabled();

    fireEvent.click(compareButton);

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits structured resolved locations after both places are selected", async () => {
    const onSubmit = vi.fn();

    render(<TripForm onSubmit={onSubmit} isSubmitting={false} />);

    await selectOrigin();

    expect(
      screen.getByRole("button", {
        name: "Compare routes",
      }),
    ).toBeDisabled();

    await selectDestination();

    const compareButton = screen.getByRole("button", {
      name: "Compare routes",
    });

    await waitFor(() => {
      expect(compareButton).toBeEnabled();
    });

    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: /Value of time/i,
      }),
      {
        target: {
          value: "25.00",
        },
      },
    );

    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: /Fuel efficiency/i,
      }),
      {
        target: {
          value: "30",
        },
      },
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: /Gasoline grade/i,
      }),
      {
        target: {
          value: "premium",
        },
      },
    );

    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: /Gas price/i,
      }),
      {
        target: {
          value: "6.50",
        },
      },
    );

    fireEvent.click(compareButton);

    expect(onSubmit).toHaveBeenCalledTimes(1);

    expect(onSubmit).toHaveBeenCalledWith({
      origin: originLocation,
      destination: destinationLocation,
      value_of_time_per_hour: "25.00",
      gasoline: {
        fuel_efficiency_mpg: "30",
        fuel_grade: "premium",
        fuel_price_per_gallon: "6.50",
      },
    });
  });

  it("disables submission again when a selected location is edited", async () => {
    const onSubmit = vi.fn();

    render(<TripForm onSubmit={onSubmit} isSubmitting={false} />);

    await selectOrigin();
    await selectDestination();

    const compareButton = screen.getByRole("button", {
      name: "Compare routes",
    });

    await waitFor(() => {
      expect(compareButton).toBeEnabled();
    });

    const originInput = screen.getByRole("combobox", {
      name: "Origin",
    });

    fireEvent.change(originInput, {
      target: {
        value: "Edited origin",
      },
    });

    expect(compareButton).toBeDisabled();

    expect(
      screen.queryByText(
        "Both locations are resolved and ready for comparison.",
      ),
    ).not.toBeInTheDocument();

    fireEvent.click(compareButton);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
