"""Route acquisition and terrain-aware V2 trip workflow."""

from dataclasses import dataclass

from routevalue.application.models import (
    ProvidedRoute,
    RouteSearchRequest,
)
from routevalue.application.ports import RouteProvider
from routevalue.application.terrain import (
    TerrainAcquisitionResult,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_acquisition import (
    TerrainAcquisitionService,
)
from routevalue.application.terrain_preparation import (
    prepare_trip_terrain_profiles,
)
from routevalue.application.terrain_trip_evaluation import (
    TerrainTripEvaluationOrchestrator,
    TerrainTripEvaluationOutcome,
)
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
    GasolinePriceQuote,
    GasolineVehicleSpecification,
)
from routevalue.domain.units import MoneyPerHour


@dataclass(frozen=True, slots=True)
class TerrainTripWorkflowOutcome:
    """Trip evaluation and original terrain acquisition diagnostics."""

    evaluation: TerrainTripEvaluationOutcome
    acquisitions: tuple[TerrainAcquisitionResult, ...]


class TerrainTripWorkflow:
    """Compose routing, optional terrain, and V2 energy evaluation.

    A missing terrain service means terrain is disabled. No provider is
    created and no external elevation request is attempted.

    A supplied service remains responsible for enforcing its own enabled
    flag, request budget, and elevation-provider safety rules.

    This workflow does not modify V1 orchestration or API wiring.
    """

    def __init__(
        self,
        *,
        route_provider: RouteProvider,
        terrain_acquisition_service: TerrainAcquisitionService | None = None,
    ) -> None:
        self._route_provider = route_provider
        self._terrain_acquisition_service = terrain_acquisition_service
        self._evaluator = TerrainTripEvaluationOrchestrator()

    def _acquire(
        self,
        routes: tuple[ProvidedRoute, ...],
    ) -> tuple[TerrainAcquisitionResult, ...]:
        service = self._terrain_acquisition_service

        if service is None:
            return tuple(
                TerrainAcquisitionResult(
                    route_index=index,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                )
                for index in range(len(routes))
            )

        return service.acquire_routes(routes)

    def evaluate_gasoline_trip(
        self,
        request: RouteSearchRequest,
        *,
        vehicle: GasolineVehicleSpecification,
        fuel_price_quote: GasolinePriceQuote | None,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripWorkflowOutcome:
        """Route and evaluate a gasoline trip with optional terrain."""

        if value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        routes = tuple(self._route_provider.get_routes(request))
        acquisitions = self._acquire(routes)

        profiles = prepare_trip_terrain_profiles(routes, acquisitions)

        evaluation = self._evaluator.evaluate_gasoline_trip(
            routes,
            terrain_profiles=profiles,
            vehicle=vehicle,
            fuel_price_quote=fuel_price_quote,
            value_of_time_per_hour=value_of_time_per_hour,
        )

        return TerrainTripWorkflowOutcome(
            evaluation=evaluation,
            acquisitions=acquisitions,
        )

    def evaluate_electric_trip(
        self,
        request: RouteSearchRequest,
        *,
        vehicle: ElectricVehicleSpecification,
        electricity_price_quote: ElectricityPriceQuote | None,
        value_of_time_per_hour: MoneyPerHour,
    ) -> TerrainTripWorkflowOutcome:
        """Route and evaluate a BEV trip with optional terrain."""

        if value_of_time_per_hour < 0:
            raise ValueError("value_of_time_per_hour cannot be negative")

        routes = tuple(self._route_provider.get_routes(request))
        acquisitions = self._acquire(routes)

        profiles = prepare_trip_terrain_profiles(routes, acquisitions)

        evaluation = self._evaluator.evaluate_electric_trip(
            routes,
            terrain_profiles=profiles,
            vehicle=vehicle,
            electricity_price_quote=electricity_price_quote,
            value_of_time_per_hour=value_of_time_per_hour,
        )

        return TerrainTripWorkflowOutcome(
            evaluation=evaluation,
            acquisitions=acquisitions,
        )
