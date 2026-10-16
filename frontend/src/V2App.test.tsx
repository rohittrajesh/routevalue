import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import V2App from "./V2App";

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
  default: () => <div>Authentication form</div>,
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
