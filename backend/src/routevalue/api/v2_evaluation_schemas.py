"""V2-only HTTP response models for energy-aware trip evaluations."""

from datetime import datetime
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
from routevalue.api.terrain_status import V2TerrainStatusResponse
from routevalue.domain.models import GasolineGrade, GasolinePriceSource


class V2GasolinePriceResponse(BaseModel):
    """The actual trip-wide quote; missing provenance is never inferred."""

    energy_type: Literal["gasoline"] = "gasoline"
    price_per_gallon: Decimal
    fuel_grade: GasolineGrade
    source: GasolinePriceSource
    observed_at: datetime | None
    provider: str | None
    geography: str | None


class V2ElectricityPriceResponse(BaseModel):
    """The explicit electricity rate used for this trip."""

    energy_type: Literal["electricity"] = "electricity"
    price_per_kilowatt_hour: Decimal
    source: Literal["user_input", "user_preference"] = "user_input"


V2EnergyPriceResponse = Annotated[
    V2GasolinePriceResponse | V2ElectricityPriceResponse,
    Field(discriminator="energy_type"),
]


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
    """Authenticated V2 trip response with optional terrain diagnostics.

    Preserve the legacy serialized response when terrain diagnostics
    are not supplied, while exposing actual terrain status whenever
    the authenticated terrain evaluation service provides it.
    """

    route_evaluations: list[V2RouteEvaluationResponse]
    decision: DecisionResponse
    terrain_status: V2TerrainStatusResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    energy_price: V2EnergyPriceResponse | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
