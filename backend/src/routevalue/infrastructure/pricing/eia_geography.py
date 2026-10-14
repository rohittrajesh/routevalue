"""Verified geographic catalog for EIA gasoline pricing.

Only include geographic areas and grade-specific XLS series
whose availability has been independently checked.

Coordinate-to-region mapping is outside this module.
"""

from dataclasses import dataclass
from enum import StrEnum

from routevalue.application.gasoline_price_fallback import (
    GasolinePriceFallbackPlan,
)
from routevalue.domain.gasoline_price_metadata import (
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)
from routevalue.domain.models import GasolineGrade


class EiaPricingReference(StrEnum):
    """Verified geographic references supported by the initial catalog."""

    CALIFORNIA = "california"
    UNITED_STATES = "united_states"


@dataclass(frozen=True, slots=True)
class EiaGasolineRegion:
    """One verified EIA geographic dataset."""

    geography: GasolinePriceGeography
    workbook_url: str
    series_by_grade: tuple[tuple[GasolineGrade, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.geography, GasolinePriceGeography):
            raise TypeError("geography must be a GasolinePriceGeography")

        if not isinstance(self.workbook_url, str):
            raise TypeError("workbook_url must be a string")

        if not self.workbook_url.startswith("https://www.eia.gov/dnav/pet/xls/"):
            raise ValueError("unapproved EIA workbook URL")

        if not self.workbook_url.endswith(".xls"):
            raise ValueError("EIA workbook must use .xls format")

        if not isinstance(self.series_by_grade, tuple):
            raise TypeError("series_by_grade must be a tuple")

        if len(self.series_by_grade) != len(GasolineGrade):
            raise ValueError("EIA region must define all gasoline grades")

        grades: set[GasolineGrade] = set()
        series_ids: set[str] = set()

        for grade, series_id in self.series_by_grade:
            if not isinstance(grade, GasolineGrade):
                raise TypeError("invalid gasoline grade")

            if grade in grades:
                raise ValueError("duplicate gasoline grade")

            if not isinstance(series_id, str) or not series_id:
                raise ValueError("invalid EIA series identifier")

            if series_id in series_ids:
                raise ValueError("duplicate EIA series identifier")

            grades.add(grade)
            series_ids.add(series_id)

        if grades != set(GasolineGrade):
            raise ValueError("incomplete gasoline grade coverage")

    def series_for_grade(self, grade: GasolineGrade) -> str:
        """Return the verified series identifier for one grade."""

        if not isinstance(grade, GasolineGrade):
            raise TypeError("grade must be a GasolineGrade")

        for configured_grade, series_id in self.series_by_grade:
            if configured_grade is grade:
                return series_id

        raise ValueError("unsupported gasoline grade")


EIA_US_REGION = EiaGasolineRegion(
    geography=GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.NATIONAL,
        region_id="NUS",
        display_name="United States",
    ),
    workbook_url=("https://www.eia.gov/dnav/pet/xls/PET_PRI_GND_DCUS_NUS_W.xls"),
    series_by_grade=(
        (
            GasolineGrade.REGULAR,
            "EMM_EPMR_PTE_NUS_DPG",
        ),
        (
            GasolineGrade.MIDGRADE,
            "EMM_EPMM_PTE_NUS_DPG",
        ),
        (
            GasolineGrade.PREMIUM,
            "EMM_EPMP_PTE_NUS_DPG",
        ),
    ),
)


EIA_CALIFORNIA_REGION = EiaGasolineRegion(
    geography=GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.STATE,
        region_id="SCA",
        display_name="California",
    ),
    workbook_url=("https://www.eia.gov/dnav/pet/xls/PET_PRI_GND_DCUS_SCA_W.xls"),
    series_by_grade=(
        (
            GasolineGrade.REGULAR,
            "EMM_EPMR_PTE_SCA_DPG",
        ),
        (
            GasolineGrade.MIDGRADE,
            "EMM_EPMM_PTE_SCA_DPG",
        ),
        (
            GasolineGrade.PREMIUM,
            "EMM_EPMP_PTE_SCA_DPG",
        ),
    ),
)


def get_eia_region(
    reference: EiaPricingReference,
) -> EiaGasolineRegion:
    """Return a verified region without external requests."""

    if not isinstance(reference, EiaPricingReference):
        raise TypeError("reference must be an EiaPricingReference")

    if reference is EiaPricingReference.CALIFORNIA:
        return EIA_CALIFORNIA_REGION

    if reference is EiaPricingReference.UNITED_STATES:
        return EIA_US_REGION

    raise ValueError("unsupported EIA pricing reference")


def build_eia_fallback_plan(
    reference: EiaPricingReference,
) -> GasolinePriceFallbackPlan:
    """Create an approved geographic fallback plan.

    California uses the verified state dataset first,
    followed by the national dataset.

    National pricing does not fall back to unrelated regions.
    """

    if not isinstance(reference, EiaPricingReference):
        raise TypeError("reference must be an EiaPricingReference")

    if reference is EiaPricingReference.CALIFORNIA:
        return GasolinePriceFallbackPlan(
            geographies=(
                EIA_CALIFORNIA_REGION.geography,
                EIA_US_REGION.geography,
            ),
        )

    if reference is EiaPricingReference.UNITED_STATES:
        return GasolinePriceFallbackPlan(
            geographies=(EIA_US_REGION.geography,),
        )

    raise ValueError("unsupported EIA pricing reference")
