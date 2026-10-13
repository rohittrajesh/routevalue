"""M7-B2-A tests for validated vehicle mass and provenance."""

from decimal import Decimal

import pytest

from routevalue.domain.vehicle_mass import (
    POUNDS_PER_KILOGRAM,
    VehicleMass,
    VehicleMassSource,
    kilograms_to_pounds,
    pounds_to_kilograms,
)


def test_manufacturer_curb_weight_is_supported() -> None:
    mass = VehicleMass(
        kilograms=Decimal("1750.5"),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
        source_reference="manufacturer-record-123",
    )

    assert mass.kilograms == Decimal("1750.5")
    assert mass.source is VehicleMassSource.MANUFACTURER_CURB_WEIGHT
    assert mass.source_reference == "manufacturer-record-123"


def test_epa_test_weight_keeps_distinct_provenance() -> None:
    mass = VehicleMass(
        kilograms=Decimal(1900),
        source=VehicleMassSource.EPA_TEST_WEIGHT,
        source_reference="epa-test-456",
    )

    assert mass.source is VehicleMassSource.EPA_TEST_WEIGHT


def test_user_provided_mass_is_supported() -> None:
    mass = VehicleMass(
        kilograms=Decimal(1500),
        source=VehicleMassSource.USER_PROVIDED,
    )

    assert mass.source_reference is None


@pytest.mark.parametrize(
    "value",
    [
        Decimal(0),
        Decimal(-1),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_invalid_mass_is_rejected(value: Decimal) -> None:
    with pytest.raises(ValueError):
        VehicleMass(
            kilograms=value,
            source=VehicleMassSource.USER_PROVIDED,
        )


def test_float_mass_is_rejected() -> None:
    with pytest.raises(TypeError):
        VehicleMass(
            kilograms=1500.0,  # type: ignore[arg-type]
            source=VehicleMassSource.USER_PROVIDED,
        )


def test_invalid_source_is_rejected() -> None:
    with pytest.raises(TypeError):
        VehicleMass(
            kilograms=Decimal(1500),
            source="unknown",  # type: ignore[arg-type]
        )


def test_blank_source_reference_is_rejected() -> None:
    with pytest.raises(ValueError):
        VehicleMass(
            kilograms=Decimal(1500),
            source=VehicleMassSource.EPA_TEST_WEIGHT,
            source_reference=" ",
        )


def test_pounds_to_kilograms_is_precise() -> None:
    pounds = Decimal("2204.6226218487757")
    assert pounds_to_kilograms(pounds) == Decimal(1000)


def test_kilograms_to_pounds_is_precise() -> None:
    assert kilograms_to_pounds(Decimal(1000)) == (Decimal(1000) * POUNDS_PER_KILOGRAM)


def test_mass_conversion_round_trip() -> None:
    original = Decimal("1750.25")

    converted = pounds_to_kilograms(kilograms_to_pounds(original))

    assert abs(converted - original) < Decimal("1e-20")


def test_mass_is_deterministic_and_immutable() -> None:
    first = VehicleMass(
        kilograms=Decimal(2000),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )
    second = VehicleMass(
        kilograms=Decimal(2000),
        source=VehicleMassSource.MANUFACTURER_CURB_WEIGHT,
    )

    assert first == second

    with pytest.raises(AttributeError):
        first.kilograms = Decimal(3000)  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [Decimal(0), Decimal(-2), Decimal("NaN")],
)
def test_invalid_conversion_inputs(value: Decimal) -> None:
    with pytest.raises(ValueError):
        pounds_to_kilograms(value)

    with pytest.raises(ValueError):
        kilograms_to_pounds(value)
