import {
  useEffect,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
} from "react";

import "./App.css";
import "./V2App.css";

import { ApiRequestError } from "./api/tripEvaluations";
import {
  getCurrentProfile,
  getSavedVehicles,
  getUserPreferences,
  type SavedVehicle,
  type UserPreferences,
  type UserProfile,
} from "./api/v2Resources";
import {
  confirmSignIn,
  getSessionBoundary,
  isCurrentSessionPrincipal,
  requireSignIn,
  setSessionPrincipal,
  subscribeToSessionBoundary,
} from "./auth/sessionBoundary";
import AuthPanel from "./auth/AuthPanel";
import { getNeonAuthClient } from "./auth/neonClient";
import { useAuthSession } from "./auth/useAuthSession";
import PersonalizationDashboard from "./components/PersonalizationDashboard";
import V2TripPlanner from "./components/V2TripPlanner";
import AppIcon from "./components/AppIcon";
import "./WorkspaceTheme.css";

type ProfileState =
  | { status: "loading" }
  | {
      status: "ready";
      profile: UserProfile;
      vehicles: SavedVehicle[];
      preferences: UserPreferences;
    }
  | { status: "error"; message: string };

function getProfileErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (error instanceof ApiRequestError && error.status === 503) {
    return "Your account is temporarily unavailable. Please try again shortly.";
  }
  if (error instanceof ApiRequestError && error.code === "network_error") {
    return "We could not reach your account. Check your connection and retry.";
  }
  return "Could not load your RouteValue profile. Please try again.";
}

function isFailedAuthResult(value: unknown): boolean {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    value.error != null
  );
}

interface AuthenticatedWorkspaceProps {
  userEmail: string;
}

function AuthenticatedWorkspace({ userEmail }: AuthenticatedWorkspaceProps) {
  const [profileState, setProfileState] = useState<ProfileState>({
    status: "loading",
  });
  const [view, setView] = useState<"trip" | "garage" | "settings">("trip");
  const [retryVersion, setRetryVersion] = useState(0);
  const [profileRefreshError, setProfileRefreshError] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    void Promise.all([
      getCurrentProfile(),
      getSavedVehicles(),
      getUserPreferences(),
    ]).then(
      ([profile, savedVehicles, preferences]) => {
        if (active) {
          setProfileState({
            status: "ready",
            profile,
            vehicles: savedVehicles.vehicles,
            preferences,
          });
          setProfileRefreshError(false);
        }
      },
      (error: unknown) => {
        if (active) {
          setProfileState({
            status: "error",
            message: getProfileErrorMessage(error),
          });
        }
      },
    );

    return () => {
      active = false;
    };
  }, [retryVersion]);

  function navigate(next: "trip" | "garage" | "settings") {
    setView(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function retryProfile() {
    setProfileState({ status: "loading" });
    setRetryVersion((current) => current + 1);
  }

  function refreshProfileSummary() {
    void Promise.all([
      getCurrentProfile(),
      getSavedVehicles(),
      getUserPreferences(),
    ]).then(
      ([profile, savedVehicles, preferences]) => {
        setProfileState({
          status: "ready",
          profile,
          vehicles: savedVehicles.vehicles,
          preferences,
        });
        setProfileRefreshError(false);
      },
      () => {
        setProfileRefreshError(true);
      },
    );
  }

  async function handleSignOut() {
    if (isSigningOut) {
      return;
    }

    setIsSigningOut(true);
    setSignOutError(null);

    try {
      const result: unknown = await getNeonAuthClient().adapter.signOut({
        fetchOptions: {},
      });

      if (isFailedAuthResult(result)) {
        throw new Error("Sign-out rejected");
      }
      requireSignIn("signed-out");
    } catch {
      setSignOutError("Could not sign out. Please try again.");
    } finally {
      setIsSigningOut(false);
    }
  }

  const defaultVehicle =
    profileState.status === "ready"
      ? profileState.vehicles.find(
          (vehicle) => vehicle.id === profileState.profile.default_vehicle_id,
        )
      : undefined;

  return (
    <section
      className="rv-workspace"
      aria-label="Your workspace"
      data-view={view}
    >
      <aside className="rv-sidebar">
        <a className="rv-brand" href="/" aria-label="RouteValue home">
          <AppIcon name="brand" />
          RouteValue
        </a>
        <p className="rv-nav-label">YOUR WORKSPACE</p>
        <nav aria-label="Workspace">
          {(["trip", "garage", "settings"] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-current={view === item ? "page" : undefined}
              onClick={() => navigate(item)}
            >
              <AppIcon name={item} />
              {item === "trip"
                ? "Plan a trip"
                : item === "garage"
                  ? "Garage"
                  : "Preferences"}
              <span aria-hidden="true">↗</span>
            </button>
          ))}
        </nav>
        <div className="rv-sidebar-note">
          <strong>Your drive, in dollars.</strong>
          <p>
            Compare energy, tolls and your value of time. Decide what the drive
            is worth to you.
          </p>
        </div>
        <div className="rv-account">
          <span className="rv-avatar" aria-hidden="true">
            {userEmail.charAt(0).toUpperCase() || "R"}
          </span>
          <span title={userEmail}>{userEmail}</span>
        </div>
        <button
          type="button"
          className="rv-signout"
          disabled={isSigningOut}
          onClick={() => void handleSignOut()}
        >
          {isSigningOut ? "Signing out..." : "Sign out"}
        </button>
      </aside>
      <div className="rv-main">
        <header className="rv-page-header">
          <div>
            <p className="eyebrow">
              {view === "trip" ? "PERSONALIZED DRIVING COSTS" : "MAKE IT YOURS"}
            </p>
            <h1>
              {view === "trip"
                ? "Compare your driving costs."
                : view === "garage"
                  ? "Your garage."
                  : "Your preferences."}
            </h1>
            <p className="muted">
              {view === "trip"
                ? "See the cost of each route, with your priorities built in."
                : view === "garage"
                  ? "Your vehicles, ready for the road."
                  : "Set it once. Bring it on every trip."}
            </p>
          </div>
          <span className="rv-header-badge">
            <span />
            Personal workspace
          </span>
        </header>

        {signOutError && (
          <p role="alert" className="v2-feedback v2-error">
            {signOutError}
          </p>
        )}

        {profileState.status === "loading" && (
          <p role="status">Loading your saved profile...</p>
        )}

        {profileState.status === "error" && (
          <div className="v2-feedback v2-error">
            <p role="alert">{profileState.message}</p>
            <button
              type="button"
              className="v2-secondary-button"
              onClick={retryProfile}
            >
              Retry profile
            </button>
          </div>
        )}

        {profileState.status === "ready" && (
          <div className="v2-profile-content">
            <p role="status" className="rv-sr-only">
              Profile connected.
            </p>

            <dl className="v2-profile-summary">
              <div>
                <dt>
                  <AppIcon name="settings" />
                  Preferences
                </dt>
                <dd>
                  {profileState.profile.preferences_configured
                    ? "Configured"
                    : "Not configured yet"}
                </dd>
              </div>
              <div>
                <dt>
                  <AppIcon name="garage" />
                  Default vehicle
                </dt>
                <dd>
                  {defaultVehicle
                    ? `${defaultVehicle.year} ${defaultVehicle.make} ${defaultVehicle.model}`
                    : profileState.profile.default_vehicle_id
                      ? "Saved vehicle selected"
                      : "Not selected"}
                </dd>
              </div>
            </dl>

            {profileRefreshError && (
              <p role="alert" className="m9-note">
                Your account summary could not refresh. The settings below
                remain available.
              </p>
            )}

            <div className="rv-view" hidden={view === "trip"}>
              <PersonalizationDashboard
                view={view === "garage" ? "garage" : "settings"}
                onProfileChanged={refreshProfileSummary}
              />
            </div>
            <div className="rv-view" hidden={view !== "trip"}>
              <div className="rv-trip-intro">
                <div>
                  <span className="rv-kicker">
                    COST INSIGHTS FOR YOUR DRIVE
                  </span>
                  <h2>
                    Energy. Tolls. <em>Your time.</em>
                  </h2>
                  <p>One cost breakdown, built around your priorities.</p>
                </div>
                <div className="rv-route-art" aria-hidden="true">
                  <span className="rv-art-pin">A</span>
                  <svg viewBox="0 0 320 140">
                    <path d="M25 110C90 110 30 25 125 25S210 125 295 35" />
                  </svg>
                  <span className="rv-art-pin">B</span>
                </div>
              </div>
              <div className="rv-quick-actions">
                <button type="button" onClick={() => navigate("garage")}>
                  <AppIcon name="garage" />
                  {profileState.vehicles.length
                    ? "Manage vehicles"
                    : "Add your first vehicle"}
                  <span aria-hidden="true">↗</span>
                </button>
                <button type="button" onClick={() => navigate("settings")}>
                  <AppIcon name="settings" />
                  {profileState.preferences.value_of_time_per_hour == null
                    ? "Set your value of time"
                    : "Adjust your preferences"}
                  <span aria-hidden="true">↗</span>
                </button>
              </div>

              <V2TripPlanner
                vehicles={profileState.vehicles}
                preferences={profileState.preferences}
              />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function V2App() {
  const session = useAuthSession();
  const boundary = useSyncExternalStore(
    subscribeToSessionBoundary,
    getSessionBoundary,
  );
  useLayoutEffect(() => {
    setSessionPrincipal(session.userId);
  }, [session.userId]);
  const needsSignIn = boundary.reason !== null;

  return (
    <main
      className={`app-shell v2-app ${session.status === "authenticated" && !needsSignIn ? "rv-signed-in" : "rv-signed-out"}`}
    >
      {(session.status !== "authenticated" || needsSignIn) && (
        <header className="hero v2-hero">
          <a className="brand" href="/" aria-label="RouteValue home">
            <AppIcon name="brand" />
            RouteValue
          </a>

          <div className="hero-copy">
            <p className="eyebrow">PERSONALIZED DRIVING COSTS</p>
            <h1>
              Know the cost.
              <br />
              Choose <em>what matters.</em>
            </h1>
            <p className="hero-description">
              Compare fuel or charging, tolls and travel time in one
              personalized cost breakdown. Set what your time is worth, then see
              when a longer drive could cost you less.
            </p>
          </div>
          <div className="rv-auth-features">
            <span>01 / Your vehicle</span>
            <span>02 / Your value of time</span>
            <span>03 / Your cost breakdown</span>
          </div>
        </header>
      )}

      {session.status === "loading" && (
        <section className="v2-auth-card" role="status">
          Checking your session...
        </section>
      )}

      {session.status === "error" && (
        <section className="v2-auth-card">
          <h2>Session unavailable</h2>
          <p role="alert">We could not verify your authentication session.</p>
          <a href="/v2">Reload and try again</a>
        </section>
      )}

      {(session.status === "unauthenticated" || needsSignIn) && (
        <div className="rv-auth-entry">
          {boundary.reason === "expired" && (
            <p role="alert">Your session has expired. Please sign in again.</p>
          )}
          <AuthPanel onSignedIn={confirmSignIn} />
        </div>
      )}

      {session.status === "authenticated" &&
        !needsSignIn &&
        isCurrentSessionPrincipal(session.userId) && (
          <AuthenticatedWorkspace
            key={session.userId}
            userEmail={session.userEmail ?? ""}
          />
        )}
    </main>
  );
}
