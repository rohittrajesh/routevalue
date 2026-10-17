"""Map application trip results to V2-specific energy-aware responses."""

from routevalue.api.mappers import to_trip_evaluation_response
from routevalue.api.terrain_status import V2TerrainStatusResponse
from routevalue.api.v2_evaluation_schemas import (
    V2ElectricConsumptionResponse,
    V2EnergyEstimateResponse,
    V2GasolineConsumptionResponse,
    V2RouteEvaluationResponse,
    V2TripEvaluationResponse,
)
from routevalue.application.models import TripEvaluationResult
from routevalue.domain.models import (
    ElectricConsumption,
    EnergyEstimate,
    GasolineConsumption,
)


def _to_v2_energy_estimate(
    estimate: EnergyEstimate | None,
) -> V2EnergyEstimateResponse | None:
    """Preserve monetary cost and map physical energy without guessing."""

    if estimate is None:
        return None

    consumption = estimate.consumption

    physical_consumption: V2GasolineConsumptionResponse | V2ElectricConsumptionResponse | None

    if isinstance(consumption, GasolineConsumption):
        physical_consumption = V2GasolineConsumptionResponse(
            energy_type="gasoline",
            gallons=consumption.gallons,
        )

    elif isinstance(consumption, ElectricConsumption):
        physical_consumption = V2ElectricConsumptionResponse(
            energy_type="electricity",
            kilowatt_hours=consumption.kilowatt_hours,
        )

    elif consumption is None:
        physical_consumption = None

    else:
        raise TypeError("unsupported physical energy consumption type")

    return V2EnergyEstimateResponse(
        cost=estimate.cost,
        consumption=physical_consumption,
    )


def to_v2_trip_evaluation_response(
    result: TripEvaluationResult,
    *,
    terrain_status: V2TerrainStatusResponse | None = None,
) -> V2TripEvaluationResponse:
    """Map V2 evaluation without changing physical-energy semantics."""

    common_response = to_trip_evaluation_response(result)

    evaluations = [
        V2RouteEvaluationResponse(
            route=common.route,
            energy_estimate=_to_v2_energy_estimate(application.energy_estimate),
            eligibility=common.eligibility,
            cost_breakdown=common.cost_breakdown,
            geometry=common.geometry,
        )
        for common, application in zip(
            common_response.route_evaluations,
            result.route_evaluations,
            strict=True,
        )
    ]

    return V2TripEvaluationResponse(
        route_evaluations=evaluations,
        decision=common_response.decision,
        terrain_status=terrain_status,
    )
