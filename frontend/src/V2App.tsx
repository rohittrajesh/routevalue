import { useEffect, useState } from "react";

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
import AuthPanel from "./auth/AuthPanel";
import { getNeonAuthClient } from "./auth/neonClient";
import { useAuthSession } from "./auth/useAuthSession";
import PersonalizationDashboard from "./components/PersonalizationDashboard";
import V2TripPlanner from "./components/V2TripPlanner";

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
    return "Authentication or the API is temporarily unavailable.";
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
      className="v2-auth-card v2-workspace-card"
      aria-labelledby="v2-profile-title"
    >
      <div className="v2-account-header">
        <div>
          <p className="eyebrow">Authenticated account</p>
          <h2 id="v2-profile-title">Your RouteValue profile</h2>
          <p className="muted">{userEmail}</p>
        </div>

        <button
          type="button"
          className="v2-secondary-button"
          disabled={isSigningOut}
          onClick={() => void handleSignOut()}
        >
          {isSigningOut ? "Signing out..." : "Sign out"}
        </button>
      </div>

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
          <p role="status" className="v2-success">
            Profile connected.
          </p>

          <dl className="v2-profile-summary">
            <div>
              <dt>Preferences</dt>
              <dd>
                {profileState.profile.preferences_configured
                  ? "Configured"
                  : "Not configured yet"}
              </dd>
            </div>
            <div>
              <dt>Default vehicle</dt>
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
              Your account summary could not refresh. The settings below remain
              available.
            </p>
          )}

          <PersonalizationDashboard onProfileChanged={refreshProfileSummary} />

          <V2TripPlanner
            vehicles={profileState.vehicles}
            preferences={profileState.preferences}
          />
        </div>
      )}
    </section>
  );
}

export default function V2App() {
  const session = useAuthSession();

  return (
    <main className="app-shell v2-app">
      <header className="hero v2-hero">
        <a className="brand" href="/" aria-label="RouteValue home">
          RouteValue
        </a>

        <div className="hero-copy">
          <p className="eyebrow">RouteValue V2</p>
          <h1>Drive smarter, with your own preferences.</h1>
          <p className="hero-description">
            Save your vehicle, personalize the value of your time, and compare
            routes using total driving cost.
          </p>
        </div>
      </header>

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

      {session.status === "unauthenticated" && <AuthPanel />}

      {session.status === "authenticated" && (
        <AuthenticatedWorkspace
          key={session.userId}
          userEmail={session.userEmail ?? ""}
        />
      )}
    </main>
  );
}
