"""M8 EIA XLS parser regression tests using in-memory workbooks."""

from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
import xlwt  # type: ignore[import-untyped]

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaXlsParseError,
    EiaXlsParseFailureReason,
)
from routevalue.infrastructure.pricing.eia_xls_parser import (
    parse_eia_xls_workbook,
)

DATE_STYLE = xlwt.easyxf(num_format_str="YYYY-MM-DD")


def make_workbook(
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    *,
    missing_sheet: bool = False,
    missing_grade: GasolineGrade | None = None,
    duplicate_premium: bool = False,
    invalid_price: bool = False,
    blank_latest: bool = False,
    reverse_dates: bool = False,
    duplicate_date: bool = False,
) -> bytes:
    """Build a small workbook with the verified EIA header layout."""

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Other" if missing_sheet else "Data 1")

    sheet.write(0, 1, "Synthetic EIA test workbook")
    sheet.write(1, 0, "Sourcekey")
    sheet.write(2, 0, "Date")

    grades = [grade for grade in GasolineGrade if grade is not missing_grade]

    for column, grade in enumerate(grades, start=1):
        sheet.write(
            1,
            column,
            region.series_for_grade(grade),
        )
        sheet.write(2, column, grade.value)

    if duplicate_premium:
        sheet.write(
            1,
            len(grades) + 1,
            region.series_for_grade(GasolineGrade.PREMIUM),
        )

    dated_values = [
        (
            datetime(2026, 9, 28),  # noqa: DTZ001 - Excel dates have no timezone
            {
                GasolineGrade.REGULAR: 6.111,
                GasolineGrade.MIDGRADE: 6.222,
                GasolineGrade.PREMIUM: 6.333,
            },
        ),
        (
            datetime(2026, 10, 5),  # noqa: DTZ001 - Excel dates have no timezone
            {
                GasolineGrade.REGULAR: 6.227,
                GasolineGrade.MIDGRADE: 6.510,
                GasolineGrade.PREMIUM: 6.677,
            },
        ),
    ]

    if reverse_dates:
        dated_values.reverse()

    if duplicate_date:
        dated_values[1] = (
            dated_values[0][0],
            dated_values[1][1],
        )

    for row, (observed_on, prices) in enumerate(
        dated_values,
        start=3,
    ):
        sheet.write(row, 0, observed_on, DATE_STYLE)

        for column, grade in enumerate(grades, start=1):
            if blank_latest and row == 4 and grade is GasolineGrade.PREMIUM:
                continue

            if invalid_price and row == 4 and grade is GasolineGrade.PREMIUM:
                sheet.write(row, column, "not-a-price")
            else:
                sheet.write(row, column, prices[grade])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_extracts_all_three_california_grades() -> None:
    observations = parse_eia_xls_workbook(
        workbook_bytes=make_workbook(),
        region=EIA_CALIFORNIA_REGION,
    )

    assert len(observations) == 3
    assert [item.fuel_grade for item in observations] == list(GasolineGrade)
    assert [str(item.price_per_gallon) for item in observations] == [
        "6.227",
        "6.51",
        "6.677",
    ]
    assert all(item.observed_on.isoformat() == "2026-10-05" for item in observations)


def test_national_region_uses_national_series() -> None:
    observations = parse_eia_xls_workbook(
        workbook_bytes=make_workbook(EIA_US_REGION),
        region=EIA_US_REGION,
    )

    assert all(item.series_id.endswith("_NUS_DPG") for item in observations)


def test_newest_observation_is_independent_of_row_order() -> None:
    observations = parse_eia_xls_workbook(
        workbook_bytes=make_workbook(reverse_dates=True),
        region=EIA_CALIFORNIA_REGION,
    )

    assert observations[0].price_per_gallon == Decimal("6.227")


def test_blank_latest_price_uses_last_populated_date() -> None:
    observations = parse_eia_xls_workbook(
        workbook_bytes=make_workbook(blank_latest=True),
        region=EIA_CALIFORNIA_REGION,
    )

    premium = observations[2]

    assert premium.fuel_grade is GasolineGrade.PREMIUM
    assert premium.observed_on.isoformat() == "2026-09-28"
    assert premium.price_per_gallon == Decimal("6.333")


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", EiaXlsParseFailureReason.INVALID_WORKBOOK),
        (
            b"not an excel workbook",
            EiaXlsParseFailureReason.INVALID_WORKBOOK,
        ),
    ],
)
def test_invalid_workbook_is_rejected(
    data: bytes,
    reason: EiaXlsParseFailureReason,
) -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=data,
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is reason


def test_missing_data_sheet_is_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(missing_sheet=True),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.MISSING_WORKSHEET


def test_missing_grade_series_is_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(missing_grade=GasolineGrade.MIDGRADE),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.MISSING_SERIES


def test_duplicate_series_is_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(duplicate_premium=True),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.DUPLICATE_SERIES


def test_invalid_populated_price_is_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(invalid_price=True),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.INVALID_PRICE


def test_duplicate_observation_date_is_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(duplicate_date=True),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.INVALID_STRUCTURE


def test_wrong_geographic_series_are_rejected() -> None:
    with pytest.raises(EiaXlsParseError) as exc:
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(EIA_US_REGION),
            region=EIA_CALIFORNIA_REGION,
        )

    assert exc.value.reason is EiaXlsParseFailureReason.MISSING_SERIES


def test_non_bytes_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="workbook_bytes"):
        parse_eia_xls_workbook(
            workbook_bytes="not bytes",  # type: ignore[arg-type]
            region=EIA_CALIFORNIA_REGION,
        )


def test_invalid_region_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaGasolineRegion"):
        parse_eia_xls_workbook(
            workbook_bytes=make_workbook(),
            region="california",  # type: ignore[arg-type]
        )
