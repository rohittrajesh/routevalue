"""Validated vehicle mass information for terrain-aware energy modeling."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

type Kilograms = Decimal

POUNDS_PER_KILOGRAM = Decimal("2.2046226218487757")


class VehicleMassSource(StrEnum):
    """Provenance of a vehicle mass observation."""

    MANUFACTURER_CURB_WEIGHT = "manufacturer_curb_weight"
    EPA_TEST_WEIGHT = "epa_test_weight"
    USER_PROVIDED = "user_provided"


@dataclass(frozen=True, slots=True)
class VehicleMass:
    """A positive mass with explicit source and physical meaning.

    EPA equivalent test weight is not the same measurement as curb
    weight. Sources remain distinguishable for future calibration.
    """

    kilograms: Kilograms
    source: VehicleMassSource
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kilograms, Decimal):
            raise TypeError("vehicle mass must be a Decimal")

        if not self.kilograms.is_finite() or self.kilograms <= 0:
            raise ValueError("vehicle mass must be finite and positive")

        if not isinstance(self.source, VehicleMassSource):
            raise TypeError("invalid vehicle mass source")

        if self.source_reference is not None:
            if not isinstance(self.source_reference, str):
                raise TypeError("source reference must be a string")

            if not self.source_reference.strip():
                raise ValueError("source reference cannot be blank")


def pounds_to_kilograms(pounds: Decimal) -> Kilograms:
    """Convert pounds to kilograms without binary floating-point arithmetic."""

    if not isinstance(pounds, Decimal):
        raise TypeError("pounds must be a Decimal")

    if not pounds.is_finite() or pounds <= 0:
        raise ValueError("pounds must be finite and positive")

    return pounds / POUNDS_PER_KILOGRAM


def kilograms_to_pounds(kilograms: Kilograms) -> Decimal:
    """Convert kilograms to pounds with Decimal precision."""

    if not isinstance(kilograms, Decimal):
        raise TypeError("kilograms must be a Decimal")

    if not kilograms.is_finite() or kilograms <= 0:
        raise ValueError("kilograms must be finite and positive")

    return kilograms * POUNDS_PER_KILOGRAM
