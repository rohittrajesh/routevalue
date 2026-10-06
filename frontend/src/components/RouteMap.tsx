import { useEffect, useMemo, useRef, useState } from "react";

import { loadCoreLibrary, loadMapsLibrary } from "../integrations/googleMaps";
import type {
  ResolvedLocationInput,
  RouteEvaluationResponse,
} from "../types/api";

interface RouteMapProps {
  routeEvaluations: RouteEvaluationResponse[];
  recommendedRouteIndex: number;
  selectedRouteIndex?: number | null;
  origin: ResolvedLocationInput;
  destination: ResolvedLocationInput;
}

interface DrawableRoute {
  index: number;
  path: google.maps.LatLngLiteral[];
}

interface RenderedPolyline {
  index: number;
  polyline: google.maps.Polyline;
}

function getDrawableRoutes(
  routeEvaluations: RouteEvaluationResponse[],
): DrawableRoute[] {
  return routeEvaluations.flatMap((evaluation, index) => {
    const geometry = evaluation.geometry;

    if (geometry === null || geometry === undefined) {
      return [];
    }

    if (geometry.points.length < 2) {
      return [];
    }

    return [
      {
        index,
        path: geometry.points.map((point) => ({
          lat: point.latitude,
          lng: point.longitude,
        })),
      },
    ];
  });
}

function getPolylineStyle(
  routeIndex: number,
  recommendedRouteIndex: number,
  selectedRouteIndex: number | null,
): google.maps.PolylineOptions {
  if (selectedRouteIndex !== null) {
    if (routeIndex !== selectedRouteIndex) {
      return {
        visible: false,
      };
    }

    const selectedRouteIsRecommended = routeIndex === recommendedRouteIndex;

    return {
      visible: true,
      strokeColor: selectedRouteIsRecommended ? "#172033" : "#68758a",
      strokeOpacity: 1,
      strokeWeight: 7,
      zIndex: 3,
    };
  }

  if (routeIndex === recommendedRouteIndex) {
    return {
      visible: true,
      strokeColor: "#172033",
      strokeOpacity: 1,
      strokeWeight: 7,
      zIndex: 3,
    };
  }

  return {
    visible: true,
    strokeColor: "#7a8699",
    strokeOpacity: 0.55,
    strokeWeight: 4,
    zIndex: 1,
  };
}

function RouteMap({
  routeEvaluations,
  recommendedRouteIndex,
  selectedRouteIndex = null,
  origin,
  destination,
}: RouteMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const renderedPolylinesRef = useRef<RenderedPolyline[]>([]);
  const endpointCirclesRef = useRef<google.maps.Circle[]>([]);

  const recommendedRouteIndexRef = useRef(recommendedRouteIndex);
  const selectedRouteIndexRef = useRef<number | null>(selectedRouteIndex);

  const [loadError, setLoadError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const drawableRoutes = useMemo(
    () => getDrawableRoutes(routeEvaluations),
    [routeEvaluations],
  );

  useEffect(() => {
    renderedPolylinesRef.current.forEach(({ polyline }) => {
      polyline.setMap(null);
    });

    renderedPolylinesRef.current = [];

    endpointCirclesRef.current.forEach((circle) => {
      circle.setMap(null);
    });

    endpointCirclesRef.current = [];

    if (drawableRoutes.length === 0 || mapContainerRef.current === null) {
      return;
    }

    let cancelled = false;

    async function initializeMap() {
      setIsLoading(true);
      setLoadError(false);

      try {
        const [mapsLibrary, coreLibrary] = await Promise.all([
          loadMapsLibrary(),
          loadCoreLibrary(),
        ]);

        if (cancelled || mapContainerRef.current === null) {
          return;
        }

        const { Circle, Map, Polyline } = mapsLibrary;
        const { LatLngBounds } = coreLibrary;

        const firstPoint = drawableRoutes[0].path[0];

        const map = new Map(mapContainerRef.current, {
          center: firstPoint,
          zoom: 10,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          gestureHandling: "cooperative",
        });

        const bounds = new LatLngBounds();

        const originPosition = {
          lat: origin.latitude,
          lng: origin.longitude,
        };

        const destinationPosition = {
          lat: destination.latitude,
          lng: destination.longitude,
        };

        bounds.extend(originPosition);
        bounds.extend(destinationPosition);

        const renderedPolylines = drawableRoutes.map((drawableRoute) => {
          drawableRoute.path.forEach((point) => {
            bounds.extend(point);
          });

          const polyline = new Polyline({
            map,
            path: drawableRoute.path,
            clickable: false,
            ...getPolylineStyle(
              drawableRoute.index,
              recommendedRouteIndexRef.current,
              selectedRouteIndexRef.current,
            ),
          });

          return {
            index: drawableRoute.index,
            polyline,
          };
        });

        renderedPolylinesRef.current = renderedPolylines;

        const originCircle = new Circle({
          map,
          center: originPosition,
          radius: 55,
          fillOpacity: 0,
          strokeColor: "#172033",
          strokeOpacity: 1,
          strokeWeight: 3,
          zIndex: 5,
        });

        const destinationCircle = new Circle({
          map,
          center: destinationPosition,
          radius: 55,
          fillOpacity: 0,
          strokeColor: "#172033",
          strokeOpacity: 1,
          strokeWeight: 3,
          zIndex: 5,
        });

        endpointCirclesRef.current = [originCircle, destinationCircle];

        map.fitBounds(bounds, 48);
      } catch {
        if (!cancelled) {
          setLoadError(true);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void initializeMap();

    return () => {
      cancelled = true;

      renderedPolylinesRef.current.forEach(({ polyline }) => {
        polyline.setMap(null);
      });

      renderedPolylinesRef.current = [];

      endpointCirclesRef.current.forEach((circle) => {
        circle.setMap(null);
      });

      endpointCirclesRef.current = [];
    };
  }, [
    destination.latitude,
    destination.longitude,
    drawableRoutes,
    origin.latitude,
    origin.longitude,
  ]);

  useEffect(() => {
    recommendedRouteIndexRef.current = recommendedRouteIndex;
    selectedRouteIndexRef.current = selectedRouteIndex;

    renderedPolylinesRef.current.forEach(({ index, polyline }) => {
      polyline.setOptions(
        getPolylineStyle(index, recommendedRouteIndex, selectedRouteIndex),
      );
    });
  }, [recommendedRouteIndex, selectedRouteIndex]);

  if (drawableRoutes.length === 0) {
    return (
      <section className="route-map-panel" aria-labelledby="route-map-title">
        <div className="route-map-heading">
          <div>
            <p className="eyebrow">Route visualization</p>
            <h3 id="route-map-title">Route map</h3>
          </div>
        </div>

        <div className="route-map-unavailable">
          Map geometry is unavailable for these routes.
        </div>
      </section>
    );
  }

  return (
    <section className="route-map-panel" aria-labelledby="route-map-title">
      <div className="route-map-heading">
        <div>
          <p className="eyebrow">Route visualization</p>
          <h3 id="route-map-title">Route map</h3>
        </div>

        <div className="route-map-context">
          {recommendedRouteIndex >= 0 && (
            <span>
              Route {recommendedRouteIndex + 1} is the RouteValue recommendation
            </span>
          )}

          {selectedRouteIndex !== null && (
            <strong>Inspecting Route {selectedRouteIndex + 1}</strong>
          )}

          <div className="route-map-endpoints" aria-label="Map endpoint legend">
            <span>
              <i className="route-map-origin-dot" />
              Origin
            </span>

            <span>
              <i className="route-map-destination-dot" />
              Destination
            </span>
          </div>
        </div>
      </div>

      <div
        ref={mapContainerRef}
        className="route-map-canvas"
        aria-label="Map showing the evaluated route alternatives"
      />

      {isLoading && (
        <p className="route-map-status" role="status">
          Loading route map…
        </p>
      )}

      {loadError && (
        <p className="route-map-status route-map-error" role="alert">
          The route comparison is available, but the map could not be loaded.
        </p>
      )}
    </section>
  );
}

export default RouteMap;
