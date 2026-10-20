import type { ApiErrorResponse } from "../types/api";

import { getV2ApiBaseUrl } from "./config";
import { ApiRequestError } from "./tripEvaluations";

export interface AuthenticatedRequestOptions {
  token: string | null;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

function isApiErrorResponse(value: unknown): value is ApiErrorResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  return (
    "code" in value &&
    typeof value.code === "string" &&
    "detail" in value &&
    typeof value.detail === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function authenticatedV2Request<T>(
  path: string,
  options: AuthenticatedRequestOptions,
): Promise<T> {
  const token = options.token;

  if (token === null || token.length === 0 || token.trim() !== token) {
    throw new ApiRequestError(
      "Please sign in to continue.",
      401,
      "authentication_required",
    );
  }

  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("Authenticated API paths must be relative.");
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;

  try {
    response = await fetch(`${getV2ApiBaseUrl()}${path}`, {
      method: options.method ?? "GET",
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) {
      throw error;
    }

    throw new ApiRequestError(
      "RouteValue could not reach the server. Check your connection and try again.",
      null,
      "network_error",
    );
  }

  if (response.status === 401) {
    throw new ApiRequestError(
      "Your session is invalid or has expired. Please sign in again.",
      401,
      "authentication_required",
    );
  }

  if (response.status === 422) {
    throw new ApiRequestError(
      "Some information is invalid. Please check your inputs.",
      422,
      "validation_error",
    );
  }

  if (!response.ok) {
    const payload = await readJson(response);

    if (isApiErrorResponse(payload)) {
      throw new ApiRequestError(payload.detail, response.status, payload.code);
    }

    throw new ApiRequestError(
      "RouteValue could not complete this request. Please try again.",
      response.status,
      "unknown_error",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await readJson(response);

  if (payload === null) {
    throw new ApiRequestError(
      "RouteValue received an unexpected response. Please try again.",
      response.status,
      "unexpected_response",
    );
  }

  return payload as T;
}
