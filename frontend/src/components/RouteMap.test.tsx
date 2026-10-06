import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ResolvedLocationInput,
  TripEvaluationResponse,
} from "../types/api";

import RouteMap from "./RouteMap";

const googleMapsMocks = vi.hoisted(() => ({
  loadMapsLibrary: vi.fn(),
  loadCoreLibrary: vi.fn(),
}));

vi.mock("../integrations/googleMaps", () => googleMapsMocks);

interface FakePolylineOptions {
  path?: google.maps.LatLngLiteral[];
  visible?: boolean;
  strokeColor?: string;
  strokeOpacity?: number;
  strokeWeight?: number;
  zIndex?: number;
}

const mapInstances: FakeMap[] = [];
const polylineInstances: FakePolyline[] = [];
const circleInstances: FakeCircle[] = [];
const boundsInstances: FakeLatLngBounds[] = [];

class FakeMap {
  fitBounds = vi.fn();

  element: HTMLElement;
  options: google.maps.MapOptions;

  constructor(element: HTMLElement, options: google.maps.MapOptions) {
    this.element = element;
    this.options = options;

    mapInstances.push(this);
  }
}

class FakePolyline {
  setMap = vi.fn();
  setOptions = vi.fn();

  options: FakePolylineOptions;

  constructor(options: FakePolylineOptions) {
    this.options = options;

    polylineInstances.push(this);
  }
}

class FakeCircle {
  setMap = vi.fn();

  options: google.maps.CircleOptions;

  constructor(options: google.maps.CircleOptions) {
    this.options = options;

    circleInstances.push(this);
  }
}

class FakeLatLngBounds {
  extend = vi.fn();

  constructor() {
    boundsInstances.push(this);
  }
}

const origin: ResolvedLocationInput = {
  display_name: "Origin Place",
  latitude: 32.88,
  longitude: -117.23,
  source: "google_places",
  source_id: "origin-place-id",
};

const destination: ResolvedLocationInput = {
  display_name: "Destination Place",
  latitude: 32.73,
  longitude: -117.19,
  source: "google_places",
  source_id: "destination-place-id",
};

const result: TripEvaluationResponse = {
  route_evaluations: [
    {
      route: {
        distance_meters: 10_000,
        duration_seconds: 900,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "2.00",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "2.00",
        time_cost: "4.50",
        generalized_cost: "6.50",
      },
      geometry: {
        points: [
          {
            latitude: 32.88,
            longitude: -117.23,
          },
          {
            latitude: 32.8,
            longitude: -117.2,
          },
        ],
      },
    },
    {
      route: {
        distance_meters: 12_000,
        duration_seconds: 800,
        toll_cost: "0",
      },
      energy_estimate: {
        cost: "3.00",
      },
      eligibility: {
        eligible: true,
        reason: null,
      },
      cost_breakdown: {
        monetary_cost: "3.00",
        time_cost: "4.00",
        generalized_cost: "7.00",
      },
      geometry: {
        points: [
          {
            latitude: 32.88,
            longitude: -117.23,
          },
          {
            latitude: 32.75,
            longitude: -117.1,
          },
        ],
      },
    },
  ],
  decision: {
    recommended_route: {
      distance_meters: 10_000,
      duration_seconds: 900,
      toll_cost: "0",
    },
    reason: "faster_and_cheaper",
    numerical_tie: false,
    missing_data_present: false,
    candidate_count: 2,
    eligible_count: 2,
  },
};

describe("RouteMap", () => {
  beforeEach(() => {
    mapInstances.length = 0;
    polylineInstances.length = 0;
    circleInstances.length = 0;
    boundsInstances.length = 0;

    googleMapsMocks.loadMapsLibrary.mockReset();
    googleMapsMocks.loadCoreLibrary.mockReset();

    googleMapsMocks.loadMapsLibrary.mockResolvedValue({
      Circle: FakeCircle,
      Map: FakeMap,
      Polyline: FakePolyline,
    });

    googleMapsMocks.loadCoreLibrary.mockResolvedValue({
      LatLngBounds: FakeLatLngBounds,
    });
  });

  it("renders every available route geometry in stable order", async () => {
    render(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances).toHaveLength(2);
    });

    expect(polylineInstances[0].options.path).toEqual([
      {
        lat: 32.88,
        lng: -117.23,
      },
      {
        lat: 32.8,
        lng: -117.2,
      },
    ]);

    expect(polylineInstances[1].options.path).toEqual([
      {
        lat: 32.88,
        lng: -117.23,
      },
      {
        lat: 32.75,
        lng: -117.1,
      },
    ]);

    expect(mapInstances).toHaveLength(1);
    expect(mapInstances[0].fitBounds).toHaveBeenCalledOnce();
  });

  it("renders origin and destination endpoint circles from resolved locations", async () => {
    render(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(circleInstances).toHaveLength(2);
    });

    expect(circleInstances[0].options.center).toEqual({
      lat: 32.88,
      lng: -117.23,
    });

    expect(circleInstances[1].options.center).toEqual({
      lat: 32.73,
      lng: -117.19,
    });

    expect(circleInstances[0].options.fillOpacity).toBe(0);
    expect(circleInstances[1].options.fillOpacity).toBe(0);

    expect(circleInstances[0].options.strokeColor).toBe("#172033");
    expect(circleInstances[1].options.strokeColor).toBe("#172033");

    expect(circleInstances[0].options.strokeWeight).toBe(3);
    expect(circleInstances[1].options.strokeWeight).toBe(3);

    expect(circleInstances[0].options.radius).toBe(55);
    expect(circleInstances[1].options.radius).toBe(55);

    expect(screen.getByText("Origin")).toBeInTheDocument();
    expect(screen.getByText("Destination")).toBeInTheDocument();

    expect(boundsInstances).toHaveLength(1);

    expect(boundsInstances[0].extend).toHaveBeenCalledWith({
      lat: 32.88,
      lng: -117.23,
    });

    expect(boundsInstances[0].extend).toHaveBeenCalledWith({
      lat: 32.73,
      lng: -117.19,
    });
  });

  it("visually emphasizes the backend-recommended route", async () => {
    render(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={1}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances).toHaveLength(2);
    });

    expect(polylineInstances[1].options.strokeWeight).toBeGreaterThan(
      polylineInstances[0].options.strokeWeight ?? 0,
    );

    expect(polylineInstances[1].options.zIndex).toBeGreaterThan(
      polylineInstances[0].options.zIndex ?? 0,
    );

    expect(polylineInstances[1].options.strokeColor).toBe("#172033");
  });

  it("renders routes that have geometry and ignores routes that do not", async () => {
    const routeEvaluations = [
      {
        ...result.route_evaluations[0],
        geometry: null,
      },
      result.route_evaluations[1],
    ];

    render(
      <RouteMap
        routeEvaluations={routeEvaluations}
        recommendedRouteIndex={1}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances).toHaveLength(1);
    });

    expect(polylineInstances[0].options.path).toEqual([
      {
        lat: 32.88,
        lng: -117.23,
      },
      {
        lat: 32.75,
        lng: -117.1,
      },
    ]);

    expect(circleInstances).toHaveLength(2);
  });

  it("keeps the textual result usable when no route has geometry", () => {
    const routeEvaluations = result.route_evaluations.map((evaluation) => ({
      ...evaluation,
      geometry: null,
    }));

    render(
      <RouteMap
        routeEvaluations={routeEvaluations}
        recommendedRouteIndex={0}
        origin={origin}
        destination={destination}
      />,
    );

    expect(
      screen.getByText(/map geometry is unavailable for these routes/i),
    ).toBeInTheDocument();

    expect(googleMapsMocks.loadMapsLibrary).not.toHaveBeenCalled();
    expect(googleMapsMocks.loadCoreLibrary).not.toHaveBeenCalled();

    expect(circleInstances).toHaveLength(0);
  });

  it("shows only the inspected alternate route without recreating the map", async () => {
    const { rerender } = render(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        selectedRouteIndex={null}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances).toHaveLength(2);
      expect(circleInstances).toHaveLength(2);
    });

    expect(mapInstances).toHaveLength(1);

    rerender(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        selectedRouteIndex={1}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances[0].setOptions).toHaveBeenCalled();
      expect(polylineInstances[1].setOptions).toHaveBeenCalled();
    });

    expect(mapInstances).toHaveLength(1);
    expect(circleInstances).toHaveLength(2);

    expect(polylineInstances[0].setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({
        visible: false,
      }),
    );

    expect(polylineInstances[1].setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({
        visible: true,
        strokeColor: "#68758a",
        strokeWeight: 7,
        zIndex: 3,
      }),
    );

    expect(screen.getByText("Inspecting Route 2")).toBeInTheDocument();
    expect(
      screen.getByText(/route 1 is the routevalue recommendation/i),
    ).toBeInTheDocument();
  });

  it("keeps the recommended route black when that route is inspected", async () => {
    const { rerender } = render(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        selectedRouteIndex={null}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances).toHaveLength(2);
    });

    rerender(
      <RouteMap
        routeEvaluations={result.route_evaluations}
        recommendedRouteIndex={0}
        selectedRouteIndex={0}
        origin={origin}
        destination={destination}
      />,
    );

    await waitFor(() => {
      expect(polylineInstances[0].setOptions).toHaveBeenCalled();
      expect(polylineInstances[1].setOptions).toHaveBeenCalled();
    });

    expect(polylineInstances[0].setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({
        visible: true,
        strokeColor: "#172033",
        strokeWeight: 7,
        zIndex: 3,
      }),
    );

    expect(polylineInstances[1].setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({
        visible: false,
      }),
    );

    expect(screen.getByText("Inspecting Route 1")).toBeInTheDocument();
  });
});
