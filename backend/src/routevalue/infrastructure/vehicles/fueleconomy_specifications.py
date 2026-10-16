"""FuelEconomy.gov vehicle-specification normalization."""

from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from routevalue.application.models import (
    VehicleSpecificationLookupResult,
    VehicleSpecificationUnavailableReason,
)
from routevalue.domain.models import (
    ElectricVehicleSpecification,
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovResponseError,
)

_FUEL_GRADE_BY_PROVIDER_VALUE = {
    "Regular Gasoline": GasolineGrade.REGULAR,
    "Midgrade Gasoline": GasolineGrade.MIDGRADE,
    "Premium Gasoline": GasolineGrade.PREMIUM,
}

_KWH_PER_100_MILES = Decimal(100)


def normalize_fueleconomy_vehicle(
    root: Element,
) -> VehicleSpecificationLookupResult:
    """Dispatch one FuelEconomy.gov vehicle record to its supported normalizer."""

    _validate_vehicle_root(root)

    advanced_vehicle_type = _vehicle_advanced_type(root)
    primary_fuel_type = _optional_text(
        root,
        "fuelType1",
    )

    if advanced_vehicle_type == "EV" or (
        advanced_vehicle_type is None and primary_fuel_type == "Electricity"
    ):
        return normalize_fueleconomy_electric_vehicle(root)

    return normalize_fueleconomy_gasoline_vehicle(root)


def normalize_fueleconomy_gasoline_vehicle(
    root: Element,
) -> VehicleSpecificationLookupResult:
    """Normalize gasoline-only vehicles, including non-plug-in hybrids."""

    _validate_vehicle_root(root)

    advanced_vehicle_type = _vehicle_advanced_type(root)

    secondary_fuel_type = _optional_text(
        root,
        "fuelType2",
    )

    # A regular or non-plug-in hybrid can use EPA gasoline MPG,
    # provided gasoline is its only listed fuel.
    # Plug-in hybrids and other advanced powertrains remain unsupported.
    if advanced_vehicle_type not in (None, "Hybrid") or secondary_fuel_type is not None:
        return _unavailable(VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN)

    primary_fuel_type = _optional_text(
        root,
        "fuelType1",
    )

    if primary_fuel_type is None:
        return _unavailable(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA)

    fuel_grade = _FUEL_GRADE_BY_PROVIDER_VALUE.get(primary_fuel_type)

    if fuel_grade is None:
        return _unavailable(VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN)

    city_mpg = _parse_positive_provider_value(
        root,
        "city08",
    )
    highway_mpg = _parse_positive_provider_value(
        root,
        "highway08",
    )
    combined_mpg = _parse_positive_provider_value(
        root,
        "comb08",
    )

    if city_mpg is None or highway_mpg is None or combined_mpg is None:
        return _unavailable(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA)

    return VehicleSpecificationLookupResult(
        specification=GasolineVehicleSpecification(
            city_mpg=city_mpg,
            highway_mpg=highway_mpg,
            combined_mpg=combined_mpg,
            fuel_grade=fuel_grade,
        ),
        unavailable_reason=None,
    )


def normalize_fueleconomy_electric_vehicle(
    root: Element,
) -> VehicleSpecificationLookupResult:
    """Normalize one battery-electric FuelEconomy.gov vehicle record."""

    _validate_vehicle_root(root)

    advanced_vehicle_type = _vehicle_advanced_type(root)

    if advanced_vehicle_type is None:
        return _unavailable(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA)

    if advanced_vehicle_type != "EV":
        return _unavailable(VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN)

    primary_fuel_type = _optional_text(
        root,
        "fuelType1",
    )

    if primary_fuel_type is None:
        return _unavailable(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA)

    if primary_fuel_type != "Electricity":
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov EV record has a non-electric primary fuel"
        )

    secondary_fuel_type = _optional_text(
        root,
        "fuelType2",
    )

    if secondary_fuel_type is not None:
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov EV record has an unexpected secondary fuel"
        )

    city_kwh_per_mile = _parse_kwh_per_mile(
        root,
        "cityE",
    )
    highway_kwh_per_mile = _parse_kwh_per_mile(
        root,
        "highwayE",
    )
    combined_kwh_per_mile = _parse_kwh_per_mile(
        root,
        "combE",
    )

    if city_kwh_per_mile is None or highway_kwh_per_mile is None or combined_kwh_per_mile is None:
        return _unavailable(VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA)

    return VehicleSpecificationLookupResult(
        specification=ElectricVehicleSpecification(
            city_kwh_per_mile=city_kwh_per_mile,
            highway_kwh_per_mile=highway_kwh_per_mile,
            combined_kwh_per_mile=combined_kwh_per_mile,
        ),
        unavailable_reason=None,
    )


def _validate_vehicle_root(
    root: Element,
) -> None:
    """Require a FuelEconomy.gov vehicle response root."""

    if root.tag != "vehicle":
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov vehicle response has an invalid root element"
        )


def _vehicle_advanced_type(
    root: Element,
) -> str | None:
    """Read FuelEconomy.gov's advanced-vehicle classification."""

    camel_case_value = _optional_text(
        root,
        "atvType",
    )
    lowercase_value = _optional_text(
        root,
        "atvtype",
    )

    if (
        camel_case_value is not None
        and lowercase_value is not None
        and camel_case_value != lowercase_value
    ):
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov vehicle response has conflicting advanced vehicle types"
        )

    return camel_case_value or lowercase_value


def _optional_text(
    root: Element,
    field_name: str,
) -> str | None:
    """Return normalized provider text or None when absent or blank."""

    value = root.findtext(field_name)

    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    return normalized


def _parse_positive_provider_value(
    root: Element,
    field_name: str,
) -> Decimal | None:
    """Parse a positive numeric provider value."""

    text = _optional_text(
        root,
        field_name,
    )

    if text is None:
        return None

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise FuelEconomyGovResponseError(
            f"FuelEconomy.gov vehicle field {field_name} is not numeric"
        ) from exc

    if not value.is_finite() or value < 0:
        raise FuelEconomyGovResponseError(f"FuelEconomy.gov vehicle field {field_name} is invalid")

    if value == 0:
        return None

    return value


def _parse_kwh_per_mile(
    root: Element,
    field_name: str,
) -> Decimal | None:
    """Convert provider kWh/100 miles to RouteValue kWh/mile."""

    kilowatt_hours_per_100_miles = _parse_positive_provider_value(
        root,
        field_name,
    )

    if kilowatt_hours_per_100_miles is None:
        return None

    return kilowatt_hours_per_100_miles / _KWH_PER_100_MILES


def _unavailable(
    reason: VehicleSpecificationUnavailableReason,
) -> VehicleSpecificationLookupResult:
    """Build an explicit unavailable specification result."""

    return VehicleSpecificationLookupResult(
        specification=None,
        unavailable_reason=reason,
    )
