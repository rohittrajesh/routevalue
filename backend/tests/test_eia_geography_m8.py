"""M8 verified EIA geographic catalog tests."""

from dataclasses import FrozenInstanceError

import pytest

from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeographicScope,
)
from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
    EiaPricingReference,
    build_eia_fallback_plan,
    get_eia_region,
)


def test_california_region_identity() -> None:
    region = EIA_CALIFORNIA_REGION

    assert region.geography.region_id == "SCA"
    assert region.geography.display_name == "California"
    assert region.geography.scope is GasolinePriceGeographicScope.STATE


def test_national_region_identity() -> None:
    region = EIA_US_REGION

    assert region.geography.region_id == "NUS"
    assert region.geography.scope is GasolinePriceGeographicScope.NATIONAL


@pytest.mark.parametrize(
    ("region", "expected_area"),
    [
        (EIA_CALIFORNIA_REGION, "SCA"),
        (EIA_US_REGION, "NUS"),
    ],
)
def test_workbook_urls_are_official(
    region: EiaGasolineRegion,
    expected_area: str,
) -> None:
    assert region.workbook_url.startswith("https://www.eia.gov/dnav/pet/xls/")
    assert f"DCUS_{expected_area}_W.xls" in region.workbook_url


@pytest.mark.parametrize(
    ("grade", "product"),
    [
        (GasolineGrade.REGULAR, "EPMR"),
        (GasolineGrade.MIDGRADE, "EPMM"),
        (GasolineGrade.PREMIUM, "EPMP"),
    ],
)
def test_california_grade_series(
    grade: GasolineGrade,
    product: str,
) -> None:
    assert EIA_CALIFORNIA_REGION.series_for_grade(grade) == f"EMM_{product}_PTE_SCA_DPG"


@pytest.mark.parametrize(
    ("grade", "product"),
    [
        (GasolineGrade.REGULAR, "EPMR"),
        (GasolineGrade.MIDGRADE, "EPMM"),
        (GasolineGrade.PREMIUM, "EPMP"),
    ],
)
def test_national_grade_series(
    grade: GasolineGrade,
    product: str,
) -> None:
    assert EIA_US_REGION.series_for_grade(grade) == f"EMM_{product}_PTE_NUS_DPG"


def test_california_plan_has_national_fallback() -> None:
    plan = build_eia_fallback_plan(EiaPricingReference.CALIFORNIA)

    assert plan.geographies == (
        EIA_CALIFORNIA_REGION.geography,
        EIA_US_REGION.geography,
    )


def test_national_plan_does_not_use_california() -> None:
    plan = build_eia_fallback_plan(EiaPricingReference.UNITED_STATES)

    assert plan.geographies == (EIA_US_REGION.geography,)


def test_repeated_plan_construction_is_deterministic() -> None:
    first = build_eia_fallback_plan(EiaPricingReference.CALIFORNIA)
    second = build_eia_fallback_plan(EiaPricingReference.CALIFORNIA)

    assert first == second


def test_unknown_region_reference_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaPricingReference"):
        get_eia_region("unknown")  # type: ignore[arg-type]


def test_unknown_plan_reference_is_rejected() -> None:
    with pytest.raises(TypeError, match="EiaPricingReference"):
        build_eia_fallback_plan(
            "unknown"  # type: ignore[arg-type]
        )


def test_catalog_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        EIA_US_REGION.workbook_url = "other"  # type: ignore[misc]


def test_duplicate_grade_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate gasoline grade"):
        EiaGasolineRegion(
            geography=EIA_US_REGION.geography,
            workbook_url=EIA_US_REGION.workbook_url,
            series_by_grade=(
                (GasolineGrade.REGULAR, "series-a"),
                (GasolineGrade.REGULAR, "series-b"),
                (GasolineGrade.PREMIUM, "series-c"),
            ),
        )


def test_unapproved_workbook_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="unapproved EIA workbook URL"):
        EiaGasolineRegion(
            geography=EIA_US_REGION.geography,
            workbook_url="https://example.com/data.xls",
            series_by_grade=EIA_US_REGION.series_by_grade,
        )
