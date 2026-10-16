import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError } from "./tripEvaluations";
import { authenticatedV2Request } from "./authenticatedClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authenticatedV2Request", () => {
  it("rejects requests without an access token", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      authenticatedV2Request("/me", { token: null }),
    ).rejects.toEqual(
      new ApiRequestError(
        "Please sign in to continue.",
        401,
        "authentication_required",
      ),
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a bearer token to the correct V2 endpoint", async () => {
    const responseBody = {
      user_id: "test-user",
      default_vehicle_id: null,
      preferences_configured: false,
    };

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(responseBody), {
        status: 200,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      authenticatedV2Request<typeof responseBody>("/me", {
        token: "test-access-token",
      }),
    ).resolves.toEqual(responseBody);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/me",
      expect.objectContaining({
        method: "GET",
        headers: {
          Authorization: "Bearer test-access-token",
        },
      }),
    );
  });

  it("sends JSON bodies for authenticated updates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          value_of_time_per_hour: "25.00",
          default_vehicle_id: null,
        }),
        {
          status: 200,
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    await authenticatedV2Request("/preferences", {
      token: "test-token",
      method: "PATCH",
      body: {
        value_of_time_per_hour: "25.00",
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/preferences",
      expect.objectContaining({
        method: "PATCH",
        headers: {
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          value_of_time_per_hour: "25.00",
        }),
      }),
    );
  });

  it("normalizes expired or invalid sessions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );

    await expect(
      authenticatedV2Request("/me", {
        token: "expired-token",
      }),
    ).rejects.toMatchObject({
      status: 401,
      code: "authentication_required",
    });
  });

  it("preserves structured backend errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "gasoline_price_stale",
            detail: "Current gasoline pricing is unavailable.",
          }),
          { status: 503 },
        ),
      ),
    );

    await expect(
      authenticatedV2Request("/trip-evaluations", {
        token: "test-token",
        method: "POST",
        body: {},
      }),
    ).rejects.toMatchObject({
      status: 503,
      code: "gasoline_price_stale",
    });
  });

  it("normalizes network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(
      authenticatedV2Request("/me", {
        token: "test-token",
      }),
    ).rejects.toMatchObject({
      status: null,
      code: "network_error",
    });
  });

  it("rejects invalid API paths", async () => {
    await expect(
      authenticatedV2Request("https://example.com", {
        token: "test-token",
      }),
    ).rejects.toThrow("Authenticated API paths must be relative.");
  });

  it("supports successful no-content responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(
      authenticatedV2Request<void>("/vehicles/test-id", {
        token: "test-token",
        method: "DELETE",
      }),
    ).resolves.toBeUndefined();
  });
});
