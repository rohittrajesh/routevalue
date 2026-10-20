const DEFAULT_API_BASE_URL = "/api";

export function getApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

  if (!configuredBaseUrl) {
    return DEFAULT_API_BASE_URL;
  }

  return configuredBaseUrl.replace(/\/+$/, "");
}

/** V2 keeps its real /api/v2 prefix when bypassing Vite's local proxy. */
export function getV2ApiBaseUrl(): string {
  const explicit = import.meta.env.VITE_V2_API_BASE_URL?.trim();
  const v1 = getApiBaseUrl();
  const configured =
    explicit ||
    (/^https?:\/\//.test(v1) ? new URL("/api/v2", v1).toString() : `${v1}/v2`);
  if (configured.includes("\\"))
    throw new Error("Invalid VITE_V2_API_BASE_URL");
  if (
    configured.startsWith("/") &&
    !configured.startsWith("//") &&
    !/[?#]/.test(configured)
  ) {
    return configured.replace(/\/+$/, "");
  }
  try {
    const url = new URL(configured);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw null;
    return url.toString().replace(/\/+$/, "");
  } catch {
    throw new Error(
      "VITE_V2_API_BASE_URL must be an HTTPS URL or same-origin path without credentials, query or fragment.",
    );
  }
}
