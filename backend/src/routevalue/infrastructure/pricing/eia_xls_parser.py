"""Strict offline parser for verified EIA weekly gasoline XLS workbooks."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import xlrd  # type: ignore[import-untyped]

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing.eia_geography import EiaGasolineRegion
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
    EiaXlsParseError,
    EiaXlsParseFailureReason,
)

DATA_SHEET_NAME = "Data 1"
SERIES_HEADER_ROW = 1
DESCRIPTION_ROW = 2
FIRST_DATA_ROW = 3
MAX_WORKBOOK_BYTES = 10 * 1024 * 1024


def _observation_date(
    cell: xlrd.sheet.Cell,
    *,
    datemode: int,
) -> date:
    """Decode a source Excel serial date without inventing a time."""

    if cell.ctype not in (xlrd.XL_CELL_DATE, xlrd.XL_CELL_NUMBER):
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_DATE)

    try:
        decoded = xlrd.xldate_as_datetime(cell.value, datemode)
    except (ValueError, TypeError, OverflowError):
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_DATE) from None

    if not isinstance(decoded, datetime):
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_DATE)

    if decoded.time() != datetime.min.time():
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_DATE)

    return decoded.date()


def _price_decimal(cell: xlrd.sheet.Cell) -> Decimal:
    """Read a populated numeric price without cent-level rounding."""

    if cell.ctype != xlrd.XL_CELL_NUMBER:
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_PRICE)

    try:
        price = Decimal(str(cell.value))
    except (InvalidOperation, ValueError, TypeError):
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_PRICE) from None

    if not price.is_finite() or price < 0:
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_PRICE)

    return price


def parse_eia_xls_workbook(
    *,
    workbook_bytes: bytes,
    region: EiaGasolineRegion,
) -> tuple[EiaGasolineObservation, ...]:
    """Extract the newest populated weekly observation for each grade.

    Enforces the region's verified exact series identifiers.
    The returned tuple follows GasolineGrade enum ordering.

    Blank historical prices are allowed, but malformed populated
    observations are not silently skipped. This function does not
    fetch data, check freshness, or create domain price quotes.
    """

    if not isinstance(workbook_bytes, bytes):
        raise TypeError("workbook_bytes must be bytes")

    if not isinstance(region, EiaGasolineRegion):
        raise TypeError("region must be an EiaGasolineRegion")

    if not workbook_bytes or len(workbook_bytes) > MAX_WORKBOOK_BYTES:
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_WORKBOOK)

    try:
        workbook = xlrd.open_workbook(file_contents=workbook_bytes)
    except (xlrd.XLRDError, ValueError, TypeError, IndexError, EOFError):
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_WORKBOOK) from None

    try:
        sheet = workbook.sheet_by_name(DATA_SHEET_NAME)
    except xlrd.XLRDError:
        raise EiaXlsParseError(EiaXlsParseFailureReason.MISSING_WORKSHEET) from None

    if sheet.nrows <= FIRST_DATA_ROW or sheet.ncols < 2:
        raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_STRUCTURE)

    required_series = {grade: region.series_for_grade(grade) for grade in GasolineGrade}

    columns: dict[str, int] = {}

    for column in range(1, sheet.ncols):
        header = sheet.cell_value(SERIES_HEADER_ROW, column)

        if not isinstance(header, str):
            continue

        series_id = header.strip()

        if series_id not in required_series.values():
            continue

        if series_id in columns:
            raise EiaXlsParseError(EiaXlsParseFailureReason.DUPLICATE_SERIES)

        columns[series_id] = column

    if any(series not in columns for series in required_series.values()):
        raise EiaXlsParseError(EiaXlsParseFailureReason.MISSING_SERIES)

    observations: list[EiaGasolineObservation] = []

    for grade in GasolineGrade:
        series_id = required_series[grade]
        column = columns[series_id]

        latest_date: date | None = None
        latest_price: Decimal | None = None
        seen_dates: set[date] = set()

        for row in range(FIRST_DATA_ROW, sheet.nrows):
            cell = sheet.cell(row, column)

            if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                continue

            observed_on = _observation_date(
                sheet.cell(row, 0),
                datemode=workbook.datemode,
            )
            price = _price_decimal(cell)

            if observed_on in seen_dates:
                raise EiaXlsParseError(EiaXlsParseFailureReason.INVALID_STRUCTURE)

            seen_dates.add(observed_on)

            if latest_date is None or observed_on > latest_date:
                latest_date = observed_on
                latest_price = price

        if latest_date is None or latest_price is None:
            raise EiaXlsParseError(EiaXlsParseFailureReason.NO_VALID_OBSERVATION)

        observations.append(
            EiaGasolineObservation(
                series_id=series_id,
                fuel_grade=grade,
                observed_on=latest_date,
                price_per_gallon=latest_price,
            )
        )

    return tuple(observations)
