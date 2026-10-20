"""Application orchestration for authenticated profile-driven trips."""

from collections.abc import Callable
from dataclasses import dataclass

from routevalue.application.electric_evaluation import (
    ElectricEvaluationContext,
    build_electric_evaluation_context,
)
from routevalue.application.gasoline_evaluation import (
    GasolineEvaluationContext,
    UnsupportedVehicleEnergyTypeError,
    build_gasoline_evaluation_context,
)
from routevalue.application.models import (
    RouteSearchRequest,
    TripEvaluationResult,
)
from routevalue.application.ports import (
    EnergyCostEstimator,
    RouteProvider,
)
from routevalue.application.profile_resolution import (
    ProfileResolutionService,
)
from routevalue.application.trip_evaluation import (
    TripEvaluationOrchestrator,
)
from routevalue.domain.identity import SavedVehicleId, UserId
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineVehicleSpecification,
)
from routevalue.domain.units import (
    MoneyPerGallon,
    MoneyPerKilowattHour,
)

type GasolineEstimatorFactory = Callable[
    [GasolineEvaluationContext],
    EnergyCostEstimator,
]

type ElectricEstimatorFactory = Callable[
    [ElectricEvaluationContext],
    EnergyCostEstimator,
]


class EnergyInputMismatchError(UnsupportedVehicleEnergyTypeError):
    """The supplied energy price does not match the saved powertrain.

    Preserve the M4 unsupported-energy exception compatibility while
    providing a specific failure for the M5 API boundary.
    """


class MissingEnergyPriceError(ValueError):
    """No usable explicit or persisted energy price is configured."""


class ElectricityPriceNotConfiguredError(MissingEnergyPriceError):
    """An EV has neither a saved rate nor an explicit trip override."""


@dataclass(frozen=True, slots=True)
class ProfileDrivenTripEvaluationService:
    """Evaluate trips using stored personalization and an owned vehicle."""

    profile_resolution_service: ProfileResolutionService
    route_provider: RouteProvider
    gasoline_estimator_factory: GasolineEstimatorFactory
    electric_estimator_factory: ElectricEstimatorFactory | None = None

    def evaluate_trip(
        self,
        user_id: UserId,
        request: RouteSearchRequest,
        *,
        fuel_price_per_gallon: MoneyPerGallon | None = None,
        price_per_kilowatt_hour: MoneyPerKilowattHour | None = None,
        requested_vehicle_id: SavedVehicleId | None = None,
    ) -> TripEvaluationResult:
        """Evaluate a trip using an owned saved vehicle's energy model.

        Accept exactly one price type. Resolve the authenticated user's
        persisted profile before checking its powertrain. Reject mismatches
        before acquiring any routes.
        """

        if fuel_price_per_gallon is not None and price_per_kilowatt_hour is not None:
            raise ValueError("exactly one energy price must be supplied")

        profile = self.profile_resolution_service.resolve_profile(
            user_id,
            requested_vehicle_id=requested_vehicle_id,
        )

        specification = profile.saved_vehicle.specification

        energy_estimator: EnergyCostEstimator

        if isinstance(specification, GasolineVehicleSpecification):
            if fuel_price_per_gallon is None:
                if price_per_kilowatt_hour is None:
                    raise MissingEnergyPriceError("exactly one energy price must be supplied")
                raise EnergyInputMismatchError("selected saved vehicle requires gasoline pricing")

            gasoline_context = build_gasoline_evaluation_context(
                profile.saved_vehicle,
                fuel_price_per_gallon=fuel_price_per_gallon,
            )

            energy_estimator = self.gasoline_estimator_factory(gasoline_context)

        elif isinstance(specification, ElectricVehicleSpecification):
            if fuel_price_per_gallon is not None:
                raise EnergyInputMismatchError(
                    "selected saved vehicle requires electricity pricing"
                )
            if price_per_kilowatt_hour is None:
                price_per_kilowatt_hour = profile.electricity_price_per_kwh
            if price_per_kilowatt_hour is None:
                raise ElectricityPriceNotConfiguredError(
                    "exactly one energy price must be supplied or saved in preferences"
                )

            electric_context = build_electric_evaluation_context(
                profile.saved_vehicle,
                price_per_kilowatt_hour=price_per_kilowatt_hour,
            )

            if self.electric_estimator_factory is None:
                raise RuntimeError("electric estimator factory is not configured")

            energy_estimator = self.electric_estimator_factory(electric_context)

        else:
            raise UnsupportedVehicleEnergyTypeError(
                "selected saved vehicle energy type is unsupported"
            )

        orchestrator = TripEvaluationOrchestrator(
            route_provider=self.route_provider,
            energy_cost_estimator=energy_estimator,
        )

        return orchestrator.evaluate_trip(
            request,
            value_of_time_per_hour=profile.value_of_time_per_hour,
        )
