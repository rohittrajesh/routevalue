from decimal import Decimal
from xml.etree.ElementTree import Element, fromstring

import pytest

from routevalue.application.models import (
    VehicleSpecificationUnavailableReason,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolineVehicleSpecification,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovResponseError,
)
from routevalue.infrastructure.vehicles.fueleconomy_specifications import (
    normalize_fueleconomy_gasoline_vehicle,
    normalize_fueleconomy_vehicle,
)


def _vehicle_xml(
    *,
    fuel_type_1: str | None = "Regular Gasoline",
    fuel_type_2: str | None = None,
    atv_type: str | None = None,
    city08: str | None = "28",
    highway08: str | None = "39",
    comb08: str | None = "32",
) -> Element:
    fields: list[str] = ["<vehicle>"]

    if atv_type is not None:
        fields.append(f"<atvType>{atv_type}</atvType>")

    if fuel_type_1 is not None:
        fields.append(f"<fuelType1>{fuel_type_1}</fuelType1>")

    if fuel_type_2 is not None:
        fields.append(f"<fuelType2>{fuel_type_2}</fuelType2>")

    if city08 is not None:
        fields.append(f"<city08>{city08}</city08>")

    if highway08 is not None:
        fields.append(f"<highway08>{highway08}</highway08>")

    if comb08 is not None:
        fields.append(f"<comb08>{comb08}</comb08>")

    fields.append("</vehicle>")

    return fromstring("".join(fields))


@pytest.mark.parametrize(
    ("provider_fuel_type", "expected_grade"),
    [
        ("Regular Gasoline", GasolineGrade.REGULAR),
        ("Midgrade Gasoline", GasolineGrade.MIDGRADE),
        ("Premium Gasoline", GasolineGrade.PREMIUM),
    ],
)
def test_normalize_gasoline_vehicle_maps_supported_fuel_grade(
    provider_fuel_type: str,
    expected_grade: GasolineGrade,
) -> None:
    result = normalize_fueleconomy_gasoline_vehicle(_vehicle_xml(fuel_type_1=provider_fuel_type))

    assert result == result.__class__(
        specification=GasolineVehicleSpecification(
            city_mpg=Decimal(28),
            highway_mpg=Decimal(39),
            combined_mpg=Decimal(32),
            fuel_grade=expected_grade,
        ),
        unavailable_reason=None,
    )


def test_normalize_gasoline_vehicle_preserves_all_mpg_values() -> None:
    result = normalize_fueleconomy_gasoline_vehicle(
        _vehicle_xml(
            city08="21.5",
            highway08="30.25",
            comb08="24.75",
        )
    )

    assert isinstance(result.specification, GasolineVehicleSpecification)
    assert result.specification.city_mpg == Decimal("21.5")
    assert result.specification.highway_mpg == Decimal("30.25")
    assert result.specification.combined_mpg == Decimal("24.75")
    assert result.specification.fuel_grade is GasolineGrade.REGULAR


def test_normalize_2021_audi_hybrid_preserves_premium_gasoline_mpg() -> None:
    result = normalize_fueleconomy_vehicle(
        _vehicle_xml(
            atv_type="Hybrid",
            fuel_type_1="Premium Gasoline",
            city08="23",
            highway08="31",
            comb08="26",
        )
    )

    assert result.unavailable_reason is None
    assert result.specification == GasolineVehicleSpecification(
        city_mpg=Decimal(23),
        highway_mpg=Decimal(31),
        combined_mpg=Decimal(26),
        fuel_grade=GasolineGrade.PREMIUM,
    )


def test_normalize_non_plugin_hybrid_accepts_regular_gasoline() -> None:
    result = normalize_fueleconomy_vehicle(
        _vehicle_xml(
            atv_type="Hybrid",
            fuel_type_1="Regular Gasoline",
            city08="50",
            highway08="45",
            comb08="48",
        )
    )

    assert isinstance(result.specification, GasolineVehicleSpecification)
    assert result.specification.combined_mpg == Decimal(48)
    assert result.specification.fuel_grade is GasolineGrade.REGULAR


@pytest.mark.parametrize(
    "atv_type",
    [
        "Plug-in Hybrid",
        "FFV",
        "Diesel",
        "CNG",
        "Bifuel (CNG)",
        "Bifuel (LPG)",
        "EV",
    ],
)
def test_normalize_gasoline_vehicle_rejects_advanced_powertrain(
    atv_type: str,
) -> None:
    result = normalize_fueleconomy_gasoline_vehicle(_vehicle_xml(atv_type=atv_type))

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


@pytest.mark.parametrize(
    "secondary_fuel",
    ["E85", "Electricity", "CNG", "LPG"],
)
def test_normalize_gasoline_vehicle_rejects_secondary_fuel(
    secondary_fuel: str,
) -> None:
    result = normalize_fueleconomy_gasoline_vehicle(_vehicle_xml(fuel_type_2=secondary_fuel))

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_hybrid_with_secondary_electricity_remains_unsupported() -> None:
    result = normalize_fueleconomy_vehicle(
        _vehicle_xml(
            atv_type="Hybrid",
            fuel_type_1="Premium Gasoline",
            fuel_type_2="Electricity",
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_hybrid_missing_mpg_remains_unavailable() -> None:
    result = normalize_fueleconomy_vehicle(
        _vehicle_xml(
            atv_type="Hybrid",
            comb08=None,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


@pytest.mark.parametrize(
    "primary_fuel",
    [
        "Diesel",
        "Electricity",
        "Natural Gas",
        "Hydrogen",
        "E85",
    ],
)
def test_normalize_gasoline_vehicle_rejects_unsupported_primary_fuel(
    primary_fuel: str,
) -> None:
    result = normalize_fueleconomy_gasoline_vehicle(_vehicle_xml(fuel_type_1=primary_fuel))

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_normalize_gasoline_vehicle_preserves_missing_fuel_type() -> None:
    result = normalize_fueleconomy_gasoline_vehicle(_vehicle_xml(fuel_type_1=None))

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


@pytest.mark.parametrize(
    ("city08", "highway08", "comb08"),
    [
        (None, "39", "32"),
        ("28", None, "32"),
        ("28", "39", None),
        ("0", "39", "32"),
        ("28", "0", "32"),
        ("28", "39", "0"),
    ],
)
def test_normalize_gasoline_vehicle_preserves_missing_efficiency(
    city08: str | None,
    highway08: str | None,
    comb08: str | None,
) -> None:
    result = normalize_fueleconomy_gasoline_vehicle(
        _vehicle_xml(
            city08=city08,
            highway08=highway08,
            comb08=comb08,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


@pytest.mark.parametrize(
    ("city08", "highway08", "comb08"),
    [
        ("not-a-number", "39", "32"),
        ("28", "NaN", "32"),
        ("28", "39", "-1"),
    ],
)
def test_normalize_gasoline_vehicle_rejects_malformed_efficiency(
    city08: str,
    highway08: str,
    comb08: str,
) -> None:
    with pytest.raises(FuelEconomyGovResponseError):
        normalize_fueleconomy_gasoline_vehicle(
            _vehicle_xml(
                city08=city08,
                highway08=highway08,
                comb08=comb08,
            )
        )


def test_normalize_gasoline_vehicle_rejects_invalid_root() -> None:
    with pytest.raises(
        FuelEconomyGovResponseError,
        match="invalid root element",
    ):
        normalize_fueleconomy_gasoline_vehicle(fromstring("<menuItems />"))


def test_normalize_gasoline_vehicle_accepts_lowercase_atvtype_field() -> None:
    root = fromstring(
        """
        <vehicle>
            <atvtype>Hybrid</atvtype>
            <fuelType1>Regular Gasoline</fuelType1>
            <city08>50</city08>
            <highway08>45</highway08>
            <comb08>48</comb08>
        </vehicle>
        """
    )

    result = normalize_fueleconomy_gasoline_vehicle(root)

    assert isinstance(result.specification, GasolineVehicleSpecification)
    assert result.specification.combined_mpg == Decimal(48)


def test_normalize_gasoline_vehicle_rejects_conflicting_atvtype_fields() -> None:
    root = fromstring(
        """
        <vehicle>
            <atvType>Hybrid</atvType>
            <atvtype>FFV</atvtype>
            <fuelType1>Regular Gasoline</fuelType1>
            <city08>50</city08>
            <highway08>45</highway08>
            <comb08>48</comb08>
        </vehicle>
        """
    )

    with pytest.raises(
        FuelEconomyGovResponseError,
        match="conflicting advanced vehicle types",
    ):
        normalize_fueleconomy_gasoline_vehicle(root)
