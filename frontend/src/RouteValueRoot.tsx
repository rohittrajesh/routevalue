import { lazy, Suspense } from "react";

import App from "./App";

const ResetPasswordPanel = lazy(() => import("./auth/ResetPasswordPanel"));
const V2App = lazy(() => import("./V2App"));

export default function RouteValueRoot() {
  const pathname = window.location.pathname;

  const recovery = pathname === "/v2/reset-password";
  const isV2Route = pathname === "/v2" || pathname === "/v2/" || recovery;

  if (!isV2Route) {
    return <App />;
  }

  return (
    <Suspense fallback={<p role="status">Loading RouteValue V2...</p>}>
      {recovery ? <ResetPasswordPanel /> : <V2App />}
    </Suspense>
  );
}
