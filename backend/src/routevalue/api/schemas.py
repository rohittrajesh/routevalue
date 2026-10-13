"""HTTP request and response schemas for the RouteValue API."""

from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class GasolineGradeInput(StrEnum):
    """Gasoline grades accepted by the public V1 API."""

    REGULAR = "regular"
    MIDGRADE = "midgrade"
    PREMIUM = "premium"


class ApiErrorCode(StrEnum):
    """Stable machine-readable error codes exposed by the public API."""

    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHENTICATION_SERVICE_UNAVAILABLE = "authentication_service_unavailable"

    ROUTING_SERVICE_UNAVAILABLE = "routing_service_unavailable"
    ROUTING_SERVICE_ERROR = "routing_service_error"
    ROUTING_RESPONSE_INVALID = "routing_response_invalid"

    SAVED_VEHICLE_NOT_FOUND = "saved_vehicle_not_found"
    SERVICE_CONFIGURATION_ERROR = "service_configuration_error"

    VEHICLE_CATALOG_RESPONSE_INVALID = "vehicle_catalog_response_invalid"
    VEHICLE_CATALOG_SERVICE_ERROR = "vehicle_catalog_service_error"
    VEHICLE_CATALOG_SERVICE_UNAVAILABLE = "vehicle_catalog_service_unavailable"
    VEHICLE_CONFIGURATION_NOT_FOUND = "vehicle_configuration_not_found"
    VEHICLE_SPECIFICATION_UNAVAILABLE = "vehicle_specification_unavailable"

    # V2-M4 profile-driven evaluation failures.
    VALUE_OF_TIME_NOT_CONFIGURED = "value_of_time_not_configured"
    DEFAULT_VEHICLE_NOT_CONFIGURED = "default_vehicle_not_configured"
    DEFAULT_VEHICLE_UNAVAILABLE = "default_vehicle_unavailable"
    UNSUPPORTED_VEHICLE_ENERGY_TYPE = "unsupported_vehicle_energy_type"
    PROFILE_SERVICE_UNAVAILABLE = "profile_service_unavailable"
    PROFILE_STATE_INVALID = "profile_state_invalid"


class ApiErrorResponse(BaseModel):
    """Stable public representation of a RouteValue request failure."""

    code: ApiErrorCode
    detail: str


class GasolineInputs(BaseModel):
    """Gasoline-specific personalization inputs for one trip evaluation."""

    fuel_efficiency_mpg: Decimal
    fuel_grade: GasolineGradeInput
    fuel_price_per_gallon: Decimal

    @field_validator("fuel_efficiency_mpg")
    @classmethod
    def fuel_efficiency_must_be_positive(cls, value: Decimal) -> Decimal:
        """Require a positive gasoline fuel-efficiency value."""

        if value <= 0:
            raise ValueError("fuel_efficiency_mpg must be greater than zero")

        return value

    @field_validator("fuel_price_per_gallon")
    @classmethod
    def fuel_price_cannot_be_negative(
        cls,
        value: Decimal,
    ) -> Decimal:
        """Reject negative user-supplied gasoline prices."""

        if value < 0:
            raise ValueError("fuel_price_per_gallon cannot be negative")

        return value


class ResolvedLocationInput(BaseModel):
    """Resolved routable location supplied by the client."""

    display_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: str | None = None
    source_id: str | None = None

    @field_validator("display_name")
    @classmethod
    def display_name_cannot_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("display_name cannot be blank")

        return value

    @field_validator(
        "source",
        "source_id",
    )
    @classmethod
    def external_reference_value_cannot_be_blank(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("external reference value cannot be blank")

        return value

    @model_validator(mode="after")
    def external_reference_must_be_complete(
        self,
    ) -> Self:
        if (self.source is None) != (self.source_id is None):
            raise ValueError("source and source_id must be provided together")

        return self


class TripEvaluationRequest(BaseModel):
    """HTTP request body for evaluating a trip."""

    origin: ResolvedLocationInput
    destination: ResolvedLocationInput
    value_of_time_per_hour: Decimal
    gasoline: GasolineInputs

    @field_validator("value_of_time_per_hour")
    @classmethod
    def value_of_time_cannot_be_negative(
        cls,
        value: Decimal,
    ) -> Decimal:
        """Reject negative values of travel time."""

        if value < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        return value


# V2-M4: Authenticated profile-driven evaluation request contracts.


class V2GasolineInputs(BaseModel):
    """Current gasoline price input for profile-driven trip evaluation."""

    model_config = {
        "extra": "forbid",
    }

    fuel_price_per_gallon: Decimal

    @field_validator("fuel_price_per_gallon")
    @classmethod
    def fuel_price_must_be_valid(
        cls,
        value: Decimal,
    ) -> Decimal:
        """Require a finite, nonnegative gasoline price."""

        if not value.is_finite():
            raise ValueError("fuel_price_per_gallon must be finite")

        if value < 0:
            raise ValueError("fuel_price_per_gallon cannot be negative")

        return value


class V2TripEvaluationRequest(BaseModel):
    """Authenticated V2 trip request using stored user personalization."""

    model_config = {
        "extra": "forbid",
    }

    origin: ResolvedLocationInput
    destination: ResolvedLocationInput
    saved_vehicle_id: UUID | None = None
    gasoline: V2GasolineInputs


class RouteResponse(BaseModel):
    """Public representation of one normalized route."""

    distance_meters: int
    duration_seconds: int
    toll_cost: Decimal | None


class RoutePointResponse(BaseModel):
    """Public representation of one normalized route-geometry point."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RouteGeometryResponse(BaseModel):
    """Public representation of normalized route geometry."""

    points: list[RoutePointResponse]


class EnergyEstimateResponse(BaseModel):
    """Public representation of a route's monetary energy estimate."""

    cost: Decimal


class CostBreakdownResponse(BaseModel):
    """Public representation of a route's personalized cost breakdown."""

    monetary_cost: Decimal
    time_cost: Decimal
    generalized_cost: Decimal


class EligibilityResponse(BaseModel):
    """Public representation of route eligibility."""

    eligible: bool
    reason: str | None


class RouteEvaluationResponse(BaseModel):
    """Public evaluation details for one route."""

    route: RouteResponse
    energy_estimate: EnergyEstimateResponse | None
    eligibility: EligibilityResponse
    cost_breakdown: CostBreakdownResponse | None
    geometry: RouteGeometryResponse | None = None


class DecisionResponse(BaseModel):
    """Public representation of the final route decision."""

    recommended_route: RouteResponse | None
    reason: str | None
    numerical_tie: bool
    missing_data_present: bool
    candidate_count: int
    eligible_count: int


class TripEvaluationResponse(BaseModel):
    """HTTP response body for one trip evaluation."""

    route_evaluations: list[RouteEvaluationResponse]
    decision: DecisionResponse


class UserPreferencesResponse(BaseModel):
    """Public V2 representation of persisted user preferences."""

    value_of_time_per_hour: Decimal | None
    default_vehicle_id: UUID | None


class UserPreferencesUpdateRequest(BaseModel):
    """Authenticated partial update to persisted V2 preferences."""

    model_config = {
        "extra": "forbid",
    }

    value_of_time_per_hour: Decimal | None = None
    default_vehicle_id: UUID | None = None

    @field_validator("value_of_time_per_hour")
    @classmethod
    def value_of_time_cannot_be_negative(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        """Reject negative persisted values of travel time."""

        if value is not None and value < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        return value

    @model_validator(mode="after")
    def update_must_contain_preference(
        self,
    ) -> Self:
        """Require PATCH requests to explicitly update at least one field."""

        if not self.model_fields_set:
            raise ValueError("at least one preference field must be provided")

        return self


class UserProfileResponse(BaseModel):
    """Public RouteValue-owned identity and profile summary."""

    user_id: UUID
    preferences_configured: bool
    default_vehicle_id: UUID | None
