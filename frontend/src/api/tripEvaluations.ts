import type {
  ApiErrorCode,
  ApiErrorResponse,
  TripEvaluationRequest,
  TripEvaluationResponse,
} from "../types/api";
import { getApiBaseUrl } from "./config";

export type ApiRequestErrorCode =
  | ApiErrorCode
  | "network_error"
  | "validation_error"
  | "unexpected_response"
  | "unknown_error";

export class ApiRequestError extends Error {
  readonly status: number | null;
  readonly code: ApiRequestErrorCode;

  constructor(
    message: string,
    status: number | null,
    code: ApiRequestErrorCode,
  ) {
    super(message);

    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

function getApiErrorResponse(payload: unknown): ApiErrorResponse | null {
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("code" in payload) ||
    typeof payload.code !== "string" ||
    !("detail" in payload) ||
    typeof payload.detail !== "string"
  ) {
    return null;
  }

  return payload as ApiErrorResponse;
}

async function getResponsePayload(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function evaluateTrip(
  request: TripEvaluationRequest,
): Promise<TripEvaluationResponse> {
  let response: Response;

  try {
    response = await fetch(`${getApiBaseUrl()}/trip-evaluations`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ApiRequestError(
      "RouteValue could not reach the server. Check your connection and try again.",
      null,
      "network_error",
    );
  }

  if (!response.ok) {
    if (response.status === 422) {
      throw new ApiRequestError(
        "Some trip information is invalid. Please check your inputs.",
        422,
        "validation_error",
      );
    }

    const payload = await getResponsePayload(response);
    const apiError = getApiErrorResponse(payload);

    if (apiError !== null) {
      throw new ApiRequestError(
        apiError.detail,
        response.status,
        apiError.code,
      );
    }

    throw new ApiRequestError(
      "RouteValue could not evaluate this trip. Please try again.",
      response.status,
      "unknown_error",
    );
  }

  try {
    return (await response.json()) as TripEvaluationResponse;
  } catch {
    throw new ApiRequestError(
      "RouteValue received an unexpected response. Please try again.",
      response.status,
      "unexpected_response",
    );
  }
}
