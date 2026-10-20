import {
  confirmSignIn,
  requireSignIn,
  setSessionPrincipal,
} from "./auth/sessionBoundary";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import V2App from "./V2App";
import { ApiRequestError } from "./api/tripEvaluations";

const { sessionMock, profileMock, vehiclesMock, preferencesMock, signOutMock } =
  vi.hoisted(() => ({
    sessionMock: vi.fn(),
    profileMock: vi.fn(),
    vehiclesMock: vi.fn(),
    preferencesMock: vi.fn(),
    signOutMock: vi.fn(),
  }));

vi.mock("./auth/useAuthSession", () => ({ useAuthSession: sessionMock }));
vi.mock("./auth/AuthPanel", () => ({
  default: ({ onSignedIn }: { onSignedIn: () => void }) => (
    <div>
      Authentication form<button onClick={onSignedIn}>Confirm sign in</button>
    </div>
  ),
}));
vi.mock("./components/PersonalizationDashboard", () => ({
  default: ({ onProfileChanged }: { onProfileChanged: () => void }) => (
    <div>
      <span>Personalization dashboard</span>
      <button type="button" onClick={onProfileChanged}>
        Refresh profile summary
      </button>
    </div>
  ),
}));
vi.mock("./components/V2TripPlanner", () => ({
  default: () => <div>Authenticated trip planner</div>,
}));
vi.mock("./api/v2Resources", () => ({
  getCurrentProfile: profileMock,
  getSavedVehicles: vehiclesMock,
  getUserPreferences: preferencesMock,
}));
vi.mock("./auth/neonClient", () => ({
  getNeonAuthClient: () => ({ adapter: { signOut: signOutMock } }),
}));

const vehicle = {
  id: "11111111-1111-4111-8111-111111111111",
  year: 2021,
  make: "Audi",
  model: "A6 quattro",
};
const profile = {
  user_id: "user-123",
  preferences_configured: true,
  default_vehicle_id: vehicle.id,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  setSessionPrincipal(null);
  confirmSignIn();
  sessionMock.mockReturnValue({
    status: "unauthenticated",
    userId: null,
    userEmail: null,
  });
  profileMock.mockResolvedValue(profile);
  vehiclesMock.mockResolvedValue({ vehicles: [vehicle] });
  preferencesMock.mockResolvedValue({
    value_of_time_per_hour: "20.50",
    default_vehicle_id: vehicle.id,
  });
  signOutMock.mockResolvedValue({ data: { success: true }, error: null });
});

function authenticated() {
  sessionMock.mockReturnValue({
    status: "authenticated",
    userId: "user-123",
    userEmail: "test@example.com",
  });
}

describe("V2App", () => {
  it("shows session loading state", () => {
    sessionMock.mockReturnValue({
      status: "loading",
      userId: null,
      userEmail: null,
    });
    render(<V2App />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking your session",
    );
    expect(profileMock).not.toHaveBeenCalled();
  });

  it("shows session verification errors", () => {
    sessionMock.mockReturnValue({
      status: "error",
      userId: null,
      userEmail: null,
    });
    render(<V2App />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not verify");
  });

  it("shows authentication for signed-out users", () => {
    render(<V2App />);
    expect(screen.getByText("Authentication form")).toBeInTheDocument();
    expect(profileMock).not.toHaveBeenCalled();
  });

  it("loads personalization and the trip planner after authentication", async () => {
    authenticated();
    render(<V2App />);
    expect(await screen.findByText("Profile connected.")).toBeInTheDocument();
    expect(screen.getByText("Personalization dashboard")).toBeInTheDocument();
    expect(screen.getByText("Authenticated trip planner")).toBeInTheDocument();
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
    expect(screen.getByText("2021 Audi A6 quattro")).toBeInTheDocument();
    expect(profileMock).toHaveBeenCalledTimes(1);
    expect(vehiclesMock).toHaveBeenCalledTimes(1);
    expect(preferencesMock).toHaveBeenCalledTimes(1);
  });

  it("retries a failed account load", async () => {
    authenticated();
    profileMock
      .mockRejectedValueOnce(new Error("Temporary failure"))
      .mockResolvedValueOnce(profile);
    const user = userEvent.setup();
    render(<V2App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load your RouteValue profile",
    );
    await user.click(screen.getByRole("button", { name: "Retry profile" }));
    expect(await screen.findByText("Profile connected.")).toBeInTheDocument();
    expect(profileMock).toHaveBeenCalledTimes(2);
  });

  it("refreshes the default vehicle name after a garage change", async () => {
    authenticated();
    vehiclesMock
      .mockResolvedValueOnce({ vehicles: [vehicle] })
      .mockResolvedValueOnce({
        vehicles: [{ ...vehicle, model: "Updated A6" }],
      });
    const user = userEvent.setup();
    render(<V2App />);
    await screen.findByText("2021 Audi A6 quattro");
    await user.click(screen.getByRole("button", { name: "Garage" }));
    await user.click(
      screen.getByRole("button", { name: "Refresh profile summary" }),
    );
    expect(await screen.findByText("2021 Audi Updated A6")).toBeInTheDocument();
    await waitFor(() => expect(profileMock).toHaveBeenCalledTimes(2));
  });

  it("requests sign-out through Neon Auth", async () => {
    authenticated();
    const user = userEvent.setup();
    render(<V2App />);
    await screen.findByText("Profile connected.");
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOutMock).toHaveBeenCalledTimes(1);
  });
});

it("removes private content after successful sign-out even if SDK state is stale", async () => {
  authenticated();
  const user = userEvent.setup();
  render(<V2App />);
  await screen.findByText("Profile connected.");
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByText("Authentication form")).toBeInTheDocument();
  expect(
    screen.queryByText("Authenticated trip planner"),
  ).not.toBeInTheDocument();
});
it("retains the workspace with a safe retry error if sign-out fails", async () => {
  authenticated();
  signOutMock.mockResolvedValueOnce({
    error: { message: "private upstream detail" },
  });
  const user = userEvent.setup();
  render(<V2App />);
  await screen.findByText("Profile connected.");
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not sign out",
  );
  expect(screen.getByText("Authenticated trip planner")).toBeInTheDocument();
  expect(screen.queryByText("private upstream detail")).not.toBeInTheDocument();
});
it("unmounts private state on expiry and reloads it after signing in again", async () => {
  authenticated();
  const user = userEvent.setup();
  render(<V2App />);
  await screen.findByText("Profile connected.");
  act(() => requireSignIn("expired"));
  expect(screen.getByRole("alert")).toHaveTextContent("session has expired");
  expect(
    screen.queryByText("Authenticated trip planner"),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Confirm sign in" }));
  expect(await screen.findByText("Profile connected.")).toBeInTheDocument();
  expect(profileMock).toHaveBeenCalledTimes(2);
});

it("opens the trip workspace and keeps the planner mounted when navigating", async () => {
  authenticated();
  const user = userEvent.setup();
  render(<V2App />);
  const planner = await screen.findByText("Authenticated trip planner");
  const trip = screen
    .getByRole("navigation", { name: "Workspace" })
    .querySelector('[aria-current="page"]');
  expect(trip).toHaveTextContent("Plan a trip");
  expect(planner).toBeVisible();
  expect(screen.getAllByRole("link", { name: "RouteValue home" })).toHaveLength(
    1,
  );
  expect(screen.queryByText("RouteValue V2")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Preferences" }));
  expect(planner).not.toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Your preferences." }),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: /^Plan a trip/ }));
  expect(screen.getByText("Authenticated trip planner")).toBe(planner);
  expect(planner).toBeVisible();
});

it.each([
  [
    new ApiRequestError("private network detail", null, "network_error"),
    "Check your connection and retry",
  ],
  [
    new ApiRequestError("private upstream detail", 503, "unknown_error"),
    "temporarily unavailable",
  ],
])(
  "explains profile availability failures without exposing upstream detail",
  async (error, message) => {
    authenticated();
    profileMock.mockRejectedValueOnce(error);
    render(<V2App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Retry profile" })).toBeEnabled();
    expect(screen.queryByText(/private .* detail/)).not.toBeInTheDocument();
  },
);
