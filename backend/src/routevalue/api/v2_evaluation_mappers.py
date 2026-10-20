"""Map application trip results to V2-specific energy-aware responses."""

from routevalue.api.mappers import to_trip_evaluation_response
from routevalue.api.terrain_status import V2TerrainStatusResponse
from routevalue.api.v2_evaluation_schemas import (
    V2ElectricConsumptionResponse,
    V2ElectricityPriceResponse,
    V2EnergyEstimateResponse,
    V2GasolineConsumptionResponse,
    V2GasolinePriceResponse,
    V2RouteEvaluationResponse,
    V2TripEvaluationResponse,
)
from routevalue.application.models import TripEvaluationResult
from routevalue.domain.models import (
    ElectricConsumption,
    EnergyEstimate,
    EnergyPriceQuote,
    GasolineConsumption,
    GasolinePriceQuote,
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
    energy_price_quote: EnergyPriceQuote | None = None,
    electricity_price_from_preferences: bool = False,
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
        energy_price=(
            V2GasolinePriceResponse(
                price_per_gallon=energy_price_quote.price_per_gallon,
                fuel_grade=energy_price_quote.fuel_grade,
                source=energy_price_quote.source,
                observed_at=energy_price_quote.observed_at,
                provider=(
                    energy_price_quote.market_metadata.provider
                    if energy_price_quote.market_metadata
                    else None
                ),
                geography=(
                    energy_price_quote.market_metadata.geography.display_name
                    if energy_price_quote.market_metadata
                    else None
                ),
            )
            if isinstance(energy_price_quote, GasolinePriceQuote)
            else V2ElectricityPriceResponse(
                price_per_kilowatt_hour=energy_price_quote.price_per_kilowatt_hour,
                source="user_preference" if electricity_price_from_preferences else "user_input",
            )
            if energy_price_quote is not None
            else None
        ),
    )
