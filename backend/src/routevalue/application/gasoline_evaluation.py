"""Application-level gasoline context from persisted vehicle snapshots."""

from dataclasses import dataclass
from decimal import Decimal

from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.models import (
    GasolinePriceQuote,
    GasolinePriceSource,
    GasolineVehicleProfile,
    GasolineVehicleSpecification,
)
from routevalue.domain.units import MoneyPerGallon


class UnsupportedVehicleEnergyTypeError(ValueError):
    """The selected saved vehicle cannot use the M4 gasoline model."""


@dataclass(frozen=True, slots=True)
class GasolineEvaluationContext:
    """Complete gasoline inputs for the existing energy estimator."""

    vehicle: GasolineVehicleProfile
    fuel_price_quote: GasolinePriceQuote


def build_gasoline_evaluation_context(
    saved_vehicle: SavedVehicle,
    *,
    fuel_price_per_gallon: MoneyPerGallon,
) -> GasolineEvaluationContext:
    """Build gasoline context using a durable saved specification.

    The saved vehicle controls MPG and gasoline grade.
    The caller supplies only the current price per gallon.
    No vehicle catalog or network lookup is performed.
    """

    specification = saved_vehicle.specification

    if not isinstance(specification, GasolineVehicleSpecification):
        raise UnsupportedVehicleEnergyTypeError(
            "selected saved vehicle does not support gasoline evaluation"
        )

    if not isinstance(fuel_price_per_gallon, Decimal):
        raise TypeError("fuel_price_per_gallon must be a Decimal")

    if not fuel_price_per_gallon.is_finite():
        raise ValueError("fuel_price_per_gallon must be finite")

    if fuel_price_per_gallon < 0:
        raise ValueError("fuel_price_per_gallon cannot be negative")

    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=specification.combined_mpg,
        fuel_grade=specification.fuel_grade,
    )

    fuel_price_quote = GasolinePriceQuote(
        price_per_gallon=fuel_price_per_gallon,
        fuel_grade=specification.fuel_grade,
        source=GasolinePriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    return GasolineEvaluationContext(
        vehicle=vehicle,
        fuel_price_quote=fuel_price_quote,
    )
