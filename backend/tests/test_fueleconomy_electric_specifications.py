from decimal import Decimal
from xml.etree.ElementTree import Element, fromstring

import pytest

from routevalue.application.models import (
    VehicleSpecificationLookupResult,
    VehicleSpecificationUnavailableReason,
)
from routevalue.domain.models import ElectricVehicleSpecification
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovResponseError,
)
from routevalue.infrastructure.vehicles.fueleconomy_specifications import (
    normalize_fueleconomy_electric_vehicle,
)


def _electric_vehicle_xml(
    *,
    atv_type: str | None = "EV",
    fuel_type_1: str | None = "Electricity",
    fuel_type_2: str | None = None,
    city_e: str | None = "26.0",
    highway_e: str | None = "31.0",
    comb_e: str | None = "28.5",
) -> Element:
    fields: list[str] = ["<vehicle>"]

    if atv_type is not None:
        fields.append(f"<atvType>{atv_type}</atvType>")

    if fuel_type_1 is not None:
        fields.append(f"<fuelType1>{fuel_type_1}</fuelType1>")

    if fuel_type_2 is not None:
        fields.append(f"<fuelType2>{fuel_type_2}</fuelType2>")

    if city_e is not None:
        fields.append(f"<cityE>{city_e}</cityE>")

    if highway_e is not None:
        fields.append(f"<highwayE>{highway_e}</highwayE>")

    if comb_e is not None:
        fields.append(f"<combE>{comb_e}</combE>")

    fields.append("</vehicle>")

    return fromstring("".join(fields))


def test_normalize_electric_vehicle_converts_kwh_per_100_miles_to_kwh_per_mile() -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            city_e="26.0",
            highway_e="31.0",
            comb_e="28.5",
        )
    )

    assert result == VehicleSpecificationLookupResult(
        specification=ElectricVehicleSpecification(
            city_kwh_per_mile=Decimal("0.26"),
            highway_kwh_per_mile=Decimal("0.31"),
            combined_kwh_per_mile=Decimal("0.285"),
        ),
        unavailable_reason=None,
    )


def test_normalize_electric_vehicle_preserves_exact_decimal_conversion() -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            city_e="25.75",
            highway_e="30.125",
            comb_e="27.875",
        )
    )

    assert isinstance(
        result.specification,
        ElectricVehicleSpecification,
    )
    assert result.specification.city_kwh_per_mile == Decimal("0.2575")
    assert result.specification.highway_kwh_per_mile == Decimal("0.30125")
    assert result.specification.combined_kwh_per_mile == Decimal("0.27875")


def test_normalize_electric_vehicle_does_not_use_mpge_fields() -> None:
    root = fromstring(
        """
        <vehicle>
            <atvType>EV</atvType>
            <fuelType1>Electricity</fuelType1>
            <city08>999</city08>
            <highway08>888</highway08>
            <comb08>777</comb08>
            <cityE>25</cityE>
            <highwayE>30</highwayE>
            <combE>28</combE>
        </vehicle>
        """
    )

    result = normalize_fueleconomy_electric_vehicle(root)

    assert isinstance(
        result.specification,
        ElectricVehicleSpecification,
    )
    assert result.specification.city_kwh_per_mile == Decimal("0.25")
    assert result.specification.highway_kwh_per_mile == Decimal("0.30")
    assert result.specification.combined_kwh_per_mile == Decimal("0.28")


@pytest.mark.parametrize(
    "atv_type",
    [
        "Hybrid",
        "Plug-in Hybrid",
        "FFV",
        "Diesel",
        "CNG",
        "Bifuel (CNG)",
        "Bifuel (LPG)",
    ],
)
def test_normalize_electric_vehicle_rejects_non_bev_powertrain(
    atv_type: str,
) -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            atv_type=atv_type,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.UNSUPPORTED_POWERTRAIN


def test_normalize_electric_vehicle_preserves_missing_powertrain_type() -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            atv_type=None,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


def test_normalize_electric_vehicle_preserves_missing_primary_fuel() -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            fuel_type_1=None,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


@pytest.mark.parametrize(
    "primary_fuel",
    [
        "Regular Gasoline",
        "Premium Gasoline",
        "Diesel",
        "Hydrogen",
    ],
)
def test_normalize_electric_vehicle_rejects_contradictory_primary_fuel(
    primary_fuel: str,
) -> None:
    with pytest.raises(
        FuelEconomyGovResponseError,
        match="non-electric primary fuel",
    ):
        normalize_fueleconomy_electric_vehicle(
            _electric_vehicle_xml(
                fuel_type_1=primary_fuel,
            )
        )


@pytest.mark.parametrize(
    "secondary_fuel",
    [
        "Regular Gasoline",
        "E85",
        "Hydrogen",
    ],
)
def test_normalize_electric_vehicle_rejects_secondary_fuel(
    secondary_fuel: str,
) -> None:
    with pytest.raises(
        FuelEconomyGovResponseError,
        match="unexpected secondary fuel",
    ):
        normalize_fueleconomy_electric_vehicle(
            _electric_vehicle_xml(
                fuel_type_2=secondary_fuel,
            )
        )


@pytest.mark.parametrize(
    (
        "city_e",
        "highway_e",
        "comb_e",
    ),
    [
        (
            None,
            "31",
            "28.5",
        ),
        (
            "26",
            None,
            "28.5",
        ),
        (
            "26",
            "31",
            None,
        ),
        (
            "0",
            "31",
            "28.5",
        ),
        (
            "26",
            "0",
            "28.5",
        ),
        (
            "26",
            "31",
            "0",
        ),
    ],
)
def test_normalize_electric_vehicle_preserves_missing_efficiency(
    city_e: str | None,
    highway_e: str | None,
    comb_e: str | None,
) -> None:
    result = normalize_fueleconomy_electric_vehicle(
        _electric_vehicle_xml(
            city_e=city_e,
            highway_e=highway_e,
            comb_e=comb_e,
        )
    )

    assert result.specification is None
    assert result.unavailable_reason is VehicleSpecificationUnavailableReason.MISSING_REQUIRED_DATA


@pytest.mark.parametrize(
    (
        "city_e",
        "highway_e",
        "comb_e",
    ),
    [
        (
            "not-a-number",
            "31",
            "28.5",
        ),
        (
            "26",
            "NaN",
            "28.5",
        ),
        (
            "26",
            "31",
            "-1",
        ),
        (
            "Infinity",
            "31",
            "28.5",
        ),
    ],
)
def test_normalize_electric_vehicle_rejects_malformed_efficiency(
    city_e: str,
    highway_e: str,
    comb_e: str,
) -> None:
    with pytest.raises(FuelEconomyGovResponseError):
        normalize_fueleconomy_electric_vehicle(
            _electric_vehicle_xml(
                city_e=city_e,
                highway_e=highway_e,
                comb_e=comb_e,
            )
        )


def test_normalize_electric_vehicle_accepts_lowercase_atvtype_field() -> None:
    root = fromstring(
        """
        <vehicle>
            <atvtype>EV</atvtype>
            <fuelType1>Electricity</fuelType1>
            <cityE>26</cityE>
            <highwayE>31</highwayE>
            <combE>28.5</combE>
        </vehicle>
        """
    )

    result = normalize_fueleconomy_electric_vehicle(root)

    assert isinstance(
        result.specification,
        ElectricVehicleSpecification,
    )
    assert result.specification.combined_kwh_per_mile == Decimal("0.285")


def test_normalize_electric_vehicle_rejects_invalid_root() -> None:
    with pytest.raises(
        FuelEconomyGovResponseError,
        match="invalid root element",
    ):
        normalize_fueleconomy_electric_vehicle(fromstring("<menuItems />"))
