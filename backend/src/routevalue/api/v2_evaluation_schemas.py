"""V2-only HTTP response models for energy-aware trip evaluations."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from routevalue.api.schemas import (
    CostBreakdownResponse,
    DecisionResponse,
    EligibilityResponse,
    RouteGeometryResponse,
    RouteResponse,
)


class V2GasolineConsumptionResponse(BaseModel):
    """Physical gasoline consumed by a route."""

    energy_type: Literal["gasoline"]
    gallons: Decimal


class V2ElectricConsumptionResponse(BaseModel):
    """Physical electrical energy consumed by a route."""

    energy_type: Literal["electricity"]
    kilowatt_hours: Decimal


V2EnergyConsumptionResponse = Annotated[
    V2GasolineConsumptionResponse | V2ElectricConsumptionResponse,
    Field(discriminator="energy_type"),
]


class V2EnergyEstimateResponse(BaseModel):
    """Route energy cost and optional typed physical consumption."""

    cost: Decimal
    consumption: V2EnergyConsumptionResponse | None = None


class V2RouteEvaluationResponse(BaseModel):
    """V2 route evaluation including typed physical energy."""

    route: RouteResponse
    energy_estimate: V2EnergyEstimateResponse | None
    eligibility: EligibilityResponse
    cost_breakdown: CostBreakdownResponse | None
    geometry: RouteGeometryResponse | None = None


class V2TripEvaluationResponse(BaseModel):
    """Authenticated V2 trip response with typed energy information."""

    route_evaluations: list[V2RouteEvaluationResponse]
    decision: DecisionResponse
