import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";

import RouteValueRoot from "./RouteValueRoot";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouteValueRoot />
  </StrictMode>,
);
