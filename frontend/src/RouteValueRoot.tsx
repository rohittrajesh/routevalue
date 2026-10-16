import { lazy, Suspense } from "react";

import App from "./App";

const V2App = lazy(() => import("./V2App"));

export default function RouteValueRoot() {
  const pathname = window.location.pathname;

  const isV2Route = pathname === "/v2" || pathname === "/v2/";

  if (!isV2Route) {
    return <App />;
  }

  return (
    <Suspense fallback={<p role="status">Loading RouteValue V2...</p>}>
      <V2App />
    </Suspense>
  );
}
