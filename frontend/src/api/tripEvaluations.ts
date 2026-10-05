import type {
  TripEvaluationRequest,
  TripEvaluationResponse,
} from "../types/api";

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);

    this.name = "ApiRequestError";
    this.status = status;
  }
}

function getErrorMessage(payload: unknown, status: number): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }

  if (status === 422) {
    return "Some trip information is invalid. Please check your inputs.";
  }

  return "RouteValue could not evaluate this trip.";
}

export async function evaluateTrip(
  request: TripEvaluationRequest,
): Promise<TripEvaluationResponse> {
  const response = await fetch("/api/trip-evaluations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    let payload: unknown;

    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    throw new ApiRequestError(
      getErrorMessage(payload, response.status),
      response.status,
    );
  }

  return (await response.json()) as TripEvaluationResponse;
}