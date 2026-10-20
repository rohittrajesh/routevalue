import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import RouteValueRoot from "./RouteValueRoot";

vi.mock("./App", () => ({ default: () => <p>Legacy V1 planner</p> }));
vi.mock("./V2App", () => ({
  default: () => <p>Authenticated V2 application</p>,
}));
vi.mock("./auth/ResetPasswordPanel", () => ({
  default: () => <p>V2 reset link screen</p>,
}));
afterEach(() => {
  vi.unstubAllEnvs();
  window.history.replaceState(null, "", "/");
});

it("keeps the V1 homepage until explicitly enabled", () => {
  vi.stubEnv("VITE_V2_HOMEPAGE", "0");
  window.history.replaceState(null, "", "/");
  render(<RouteValueRoot />);
  expect(screen.getByText("Legacy V1 planner")).toBeInTheDocument();
});

it.each(["/", "/v2", "/v2/"])(
  "enables the V2 launch entry point %s",
  async (path) => {
    vi.stubEnv("VITE_V2_HOMEPAGE", "1");
    window.history.replaceState(null, "", path);
    render(<RouteValueRoot />);
    expect(
      await screen.findByText("Authenticated V2 application"),
    ).toBeInTheDocument();
  },
);

it.each(["/v1", "/v1/"])(
  "preserves V1 at %s when V2 is the homepage",
  (path) => {
    vi.stubEnv("VITE_V2_HOMEPAGE", "1");
    window.history.replaceState(null, "", path);
    render(<RouteValueRoot />);
    expect(screen.getByText("Legacy V1 planner")).toBeInTheDocument();
  },
);

it("preserves password reset deep links with either homepage setting", async () => {
  vi.stubEnv("VITE_V2_HOMEPAGE", "1");
  window.history.replaceState(null, "", "/v2/reset-password?token=synthetic");
  render(<RouteValueRoot />);
  expect(await screen.findByText("V2 reset link screen")).toBeInTheDocument();
});
