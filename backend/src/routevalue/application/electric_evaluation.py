"""Application-level electric context from persisted vehicle snapshots."""

from dataclasses import dataclass
from decimal import Decimal

from routevalue.application.saved_vehicles import SavedVehicle
from routevalue.domain.models import (
    ElectricityPriceQuote,
    ElectricVehicleSpecification,
)
from routevalue.domain.units import MoneyPerKilowattHour


class UnsupportedElectricVehicleEnergyTypeError(ValueError):
    """The selected saved vehicle cannot use the electric energy model."""


@dataclass(frozen=True, slots=True)
class ElectricEvaluationContext:
    """Complete electric inputs for the baseline EV estimator."""

    vehicle: ElectricVehicleSpecification
    electricity_price_quote: ElectricityPriceQuote


def build_electric_evaluation_context(
    saved_vehicle: SavedVehicle,
    *,
    price_per_kilowatt_hour: MoneyPerKilowattHour,
) -> ElectricEvaluationContext:
    """Build electric context using a durable saved BEV specification.

    Efficiency comes exclusively from the persisted vehicle snapshot.
    The caller supplies only the current electricity price.
    No vehicle catalog or network lookup is performed.
    """

    specification = saved_vehicle.specification

    if not isinstance(specification, ElectricVehicleSpecification):
        raise UnsupportedElectricVehicleEnergyTypeError(
            "selected saved vehicle does not support electric evaluation"
        )

    if not isinstance(price_per_kilowatt_hour, Decimal):
        raise TypeError("price_per_kilowatt_hour must be a Decimal")

    if not price_per_kilowatt_hour.is_finite():
        raise ValueError("price_per_kilowatt_hour must be finite")

    if price_per_kilowatt_hour < 0:
        raise ValueError("price_per_kilowatt_hour cannot be negative")

    electricity_price_quote = ElectricityPriceQuote(
        price_per_kilowatt_hour=price_per_kilowatt_hour,
    )

    return ElectricEvaluationContext(
        vehicle=specification,
        electricity_price_quote=electricity_price_quote,
    )
