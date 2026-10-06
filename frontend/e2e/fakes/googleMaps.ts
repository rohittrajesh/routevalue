class E2EMap {
  constructor(element: HTMLElement) {
    element.dataset.e2eMapReady = "true";
  }

  fitBounds(): void {}
}

class E2EPolyline {
  setMap(): void {}

  setOptions(): void {}
}

class E2ECircle {
  setMap(): void {}
}

class E2ELatLngBounds {
  extend(): void {}
}

export async function loadMapsLibrary() {
  return {
    Map: E2EMap,
    Polyline: E2EPolyline,
    Circle: E2ECircle,
  };
}

export async function loadCoreLibrary() {
  return {
    LatLngBounds: E2ELatLngBounds,
  };
}

export async function loadPlacesLibrary() {
  return {};
}
