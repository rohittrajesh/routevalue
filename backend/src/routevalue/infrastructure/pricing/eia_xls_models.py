"""Typed intermediate contracts for EIA gasoline XLS parsing.

These contracts preserve source observation dates and exact
Decimal prices without inventing publication timestamps.

Workbook decoding and domain quote construction occur in
separate layers.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from routevalue.domain.models import GasolineGrade


class EiaXlsParseFailureReason(StrEnum):
    """Reasons an EIA workbook cannot be parsed reliably."""

    INVALID_WORKBOOK = "invalid_workbook"
    MISSING_WORKSHEET = "missing_worksheet"
    INVALID_STRUCTURE = "invalid_structure"
    MISSING_SERIES = "missing_series"
    DUPLICATE_SERIES = "duplicate_series"
    INVALID_DATE = "invalid_date"
    INVALID_PRICE = "invalid_price"
    NO_VALID_OBSERVATION = "no_valid_observation"


class EiaXlsParseError(ValueError):
    """A structured failure while interpreting EIA XLS data."""

    def __init__(
        self,
        reason: EiaXlsParseFailureReason,
    ) -> None:
        if not isinstance(reason, EiaXlsParseFailureReason):
            raise TypeError("reason must be an EiaXlsParseFailureReason")

        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class EiaGasolineObservation:
    """One validated, grade-specific EIA gasoline observation.

    The source date is intentionally retained as a date.
    It must not be confused with a verified publication time.
    """

    series_id: str
    fuel_grade: GasolineGrade
    observed_on: date
    price_per_gallon: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.series_id, str):
            raise TypeError("series_id must be a string")

        if not self.series_id.strip():
            raise ValueError("series_id cannot be blank")

        if not isinstance(self.fuel_grade, GasolineGrade):
            raise TypeError("fuel_grade must be a GasolineGrade")

        if not isinstance(self.observed_on, date) or isinstance(self.observed_on, datetime):
            raise TypeError("observed_on must be a date")

        if not isinstance(self.price_per_gallon, Decimal):
            raise TypeError("price_per_gallon must be a Decimal")

        if not self.price_per_gallon.is_finite():
            raise ValueError("price_per_gallon must be finite")

        if self.price_per_gallon < 0:
            raise ValueError("price_per_gallon cannot be negative")
