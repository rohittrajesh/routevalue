export type GasolineGrade = "regular" | "midgrade" | "premium";

export interface TripEvaluationRequest {
  origin: string;
  destination: string;
  value_of_time_per_hour: string;
  gasoline: {
    fuel_efficiency_mpg: string;
    fuel_grade: GasolineGrade;
    fuel_price_per_gallon: string;
  };
}

export interface RouteResponse {
  distance_meters: number;
  duration_seconds: number;
  toll_cost: string | null;
}

export interface EnergyEstimateResponse {
  cost: string;
}

export interface EligibilityResponse {
  eligible: boolean;
  reason: string | null;
}

export interface RouteEvaluationResponse {
  route: RouteResponse;
  energy_estimate: EnergyEstimateResponse | null;
  eligibility: EligibilityResponse;
  cost_breakdown: CostBreakdownResponse | null;
}

export interface DecisionResponse {
  recommended_route: RouteResponse | null;
  reason: string | null;
  numerical_tie: boolean;
  missing_data_present: boolean;
  candidate_count: number;
  eligible_count: number;
}

export interface TripEvaluationResponse {
  route_evaluations: RouteEvaluationResponse[];
  decision: DecisionResponse;
}

export interface CostBreakdownResponse {
  monetary_cost: string;
  time_cost: string;
  generalized_cost: string;
}