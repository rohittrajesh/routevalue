"""Authenticated, profile-driven V2 terrain trip evaluation."""

from collections.abc import Callable
from dataclasses import dataclass

from routevalue.application.electric_evaluation import (
    build_electric_evaluation_context,
)
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    UnsupportedVehicleEnergyTypeError,
    build_gasoline_evaluation_context,
)
from routevalue.application.models import (
    ProvidedRoute,
    ResolvedLocation,
    RouteSearchRequest,
)
from routevalue.application.ports import RouteProvider
from routevalue.application.profile_resolution import ProfileResolutionService
from routevalue.application.profile_trip_evaluation import EnergyInputMismatchError
from routevalue.application.terrain import (
    TerrainAcquisitionResult,
    TerrainUnavailableReason,
)
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.application.terrain_geometry_policy import (
    TerrainGeometryDecision,
    evaluate_trip_terrain_geometry,
)
from routevalue.application.terrain_preparation import prepare_trip_terrain_profiles
from routevalue.application.terrain_trip_evaluation import (
    TerrainTripEvaluationOrchestrator,
    TerrainTripEvaluationOutcome,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolinePriceQuote,
    GasolineVehicleProfile,
    GasolineVehicleSpecification,
)
from routevalue.domain.units import MoneyPerGallon, MoneyPerKilowattHour

type AutomaticGasolinePriceResolver = Callable[
    [ResolvedLocation, GasolineGrade],
    GasolinePriceQuote,
]


class NoRoutesAvailableError(RuntimeError):
    """The routing provider returned no candidates for evaluation."""


@dataclass(frozen=True, slots=True)
class AuthenticatedTerrainTripOutcome:
    """Trip result with acquisition and geometry-safety diagnostics."""

    evaluation: TerrainTripEvaluationOutcome
    acquisitions: tuple[TerrainAcquisitionResult, ...]
    geometry_decision: TerrainGeometryDecision


@dataclass(frozen=True, slots=True)
class AuthenticatedTerrainTripService:
    """Evaluate authenticated trips with optional, guarded terrain data.

    Automatic gasoline pricing is optional and explicitly injected.

    Manual prices retain the existing V2 behavior. Automatic prices
    preserve their original market provenance and observation time.

    The service does not download EIA workbooks or refresh prices.
    """

    profile_resolution_service: ProfileResolutionService
    route_provider: RouteProvider
    terrain_acquisition_service: TerrainAcquisitionService | None = None
    automatic_gasoline_price_resolver: AutomaticGasolinePriceResolver | None = None

    def _acquire(
        self,
        routes: tuple[ProvidedRoute, ...],
    ) -> tuple[TerrainAcquisitionResult, ...]:
        service = self.terrain_acquisition_service

        if service is None:
            return tuple(
                TerrainAcquisitionResult(
                    route_index=index,
                    unavailable_reason=TerrainUnavailableReason.DISABLED,
                )
                for index in range(len(routes))
            )

        return service.acquire_routes(routes)

    def evaluate_trip(
        self,
        user_id: UserId,
        request: RouteSearchRequest,
        *,
        fuel_price_per_gallon: MoneyPerGallon | None = None,
        price_per_kilowatt_hour: MoneyPerKilowattHour | None = None,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> AuthenticatedTerrainTripOutcome:
        """Evaluate an owned vehicle under the trip-wide terrain policy.

        An explicit manual gasoline price has precedence over automatic
        pricing. An automatic quote is resolved once for the entire trip.

        The saved vehicle supplies the authoritative energy type,
        gasoline grade, and physical efficiency.
        """

        if fuel_price_per_gallon is not None and price_per_kilowatt_hour is not None:
            raise ValueError("exactly one energy price must be supplied")

        if (
            fuel_price_per_gallon is None
            and price_per_kilowatt_hour is None
            and self.automatic_gasoline_price_resolver is None
        ):
            raise ValueError("exactly one energy price must be supplied")

        profile = self.profile_resolution_service.resolve_profile(
            user_id,
            requested_vehicle_id=requested_vehicle_id,
        )
        specification = profile.saved_vehicle.specification

        gasoline_quote: GasolinePriceQuote | None = None
        electric_quote = None

        if isinstance(specification, GasolineVehicleSpecification):
            if price_per_kilowatt_hour is not None:
                raise EnergyInputMismatchError("selected saved vehicle requires gasoline pricing")

            if fuel_price_per_gallon is not None:
                context = build_gasoline_evaluation_context(
                    profile.saved_vehicle,
                    fuel_price_per_gallon=fuel_price_per_gallon,
                )
            else:
                resolver = self.automatic_gasoline_price_resolver

                if resolver is None:
                    raise EnergyInputMismatchError("automatic gasoline pricing is not configured")

                resolved_quote = resolver(
                    request.origin,
                    specification.fuel_grade,
                )

                if not isinstance(resolved_quote, GasolinePriceQuote):
                    raise TypeError("automatic gasoline resolver must return a GasolinePriceQuote")

                if resolved_quote.fuel_grade is not specification.fuel_grade:
                    raise ValueError(
                        "automatic gasoline quote grade does not match the saved vehicle"
                    )

                context = GasolineEvaluationContext(
                    vehicle=GasolineVehicleProfile(
                        fuel_efficiency_mpg=specification.combined_mpg,
                        fuel_grade=specification.fuel_grade,
                    ),
                    fuel_price_quote=resolved_quote,
                )

            gasoline_quote = context.fuel_price_quote

        elif isinstance(specification, ElectricVehicleSpecification):
            if price_per_kilowatt_hour is None:
                raise EnergyInputMismatchError(
                    "selected saved vehicle requires electricity pricing"
                )

            context_electric = build_electric_evaluation_context(
                profile.saved_vehicle,
                price_per_kilowatt_hour=price_per_kilowatt_hour,
            )
            electric_quote = context_electric.electricity_price_quote

        else:
            raise UnsupportedVehicleEnergyTypeError(
                "selected saved vehicle energy type is unsupported"
            )

        routes = tuple(self.route_provider.get_routes(request))

        if not routes:
            raise NoRoutesAvailableError("routing provider returned no candidate routes")

        acquisitions = self._acquire(routes)
        profiles = prepare_trip_terrain_profiles(routes, acquisitions)

        geometry_decision = evaluate_trip_terrain_geometry(profiles)

        # Missing or untrusted geometry forces a shared baseline.
        safe_profiles = profiles if geometry_decision.allowed else (None,) * len(routes)

        evaluator = TerrainTripEvaluationOrchestrator()

        if isinstance(specification, GasolineVehicleSpecification):
            assert gasoline_quote is not None

            evaluation = evaluator.evaluate_gasoline_trip(
                routes,
                terrain_profiles=safe_profiles,
                vehicle=specification,
                fuel_price_quote=gasoline_quote,
                value_of_time_per_hour=profile.value_of_time_per_hour,
            )
        else:
            assert isinstance(specification, ElectricVehicleSpecification)
            assert electric_quote is not None

            evaluation = evaluator.evaluate_electric_trip(
                routes,
                terrain_profiles=safe_profiles,
                vehicle=specification,
                electricity_price_quote=electric_quote,
                value_of_time_per_hour=profile.value_of_time_per_hour,
            )

        return AuthenticatedTerrainTripOutcome(
            evaluation=evaluation,
            acquisitions=acquisitions,
            geometry_decision=geometry_decision,
        )
