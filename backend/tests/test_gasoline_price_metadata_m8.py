"""M8 geographic gasoline pricing and provenance tests."""

from datetime import UTC, datetime

import pytest

from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
    GasolinePriceGeographicScope,
    GasolinePriceGeography,
)


def make_geography() -> GasolinePriceGeography:
    return GasolinePriceGeography(
        scope=GasolinePriceGeographicScope.REGION,
        region_id="test-region",
        display_name="Test Region",
    )


def test_geography_preserves_region_identity() -> None:
    geography = make_geography()

    assert geography.scope is GasolinePriceGeographicScope.REGION
    assert geography.region_id == "test-region"
    assert geography.display_name == "Test Region"


@pytest.mark.parametrize(
    "scope",
    list(GasolinePriceGeographicScope),
)
def test_all_supported_geographic_scopes(
    scope: GasolinePriceGeographicScope,
) -> None:
    geography = GasolinePriceGeography(
        scope=scope,
        region_id="example",
        display_name="Example",
    )

    assert geography.scope is scope


def test_geography_rejects_invalid_scope() -> None:
    with pytest.raises(TypeError, match="must be a"):
        GasolinePriceGeography(
            scope="region",  # type: ignore[arg-type]
            region_id="example",
            display_name="Example",
        )


@pytest.mark.parametrize(
    "value",
    ["", " ", "  region", "region  "],
)
def test_geography_rejects_invalid_region_id(value: str) -> None:
    with pytest.raises(ValueError):
        GasolinePriceGeography(
            scope=GasolinePriceGeographicScope.REGION,
            region_id=value,
            display_name="Example",
        )


def test_geography_rejects_blank_display_name() -> None:
    with pytest.raises(ValueError, match="display_name"):
        GasolinePriceGeography(
            scope=GasolinePriceGeographicScope.STATE,
            region_id="example",
            display_name=" ",
        )


def test_market_metadata_preserves_provider() -> None:
    metadata = GasolineMarketMetadata(
        provider="EIA",
        geography=make_geography(),
    )

    assert metadata.provider == "EIA"
    assert metadata.published_at is None


def test_market_metadata_accepts_aware_publication_time() -> None:
    published_at = datetime(2026, 10, 12, tzinfo=UTC)

    metadata = GasolineMarketMetadata(
        provider="EIA",
        geography=make_geography(),
        published_at=published_at,
    )

    assert metadata.published_at == published_at


def test_market_metadata_rejects_blank_provider() -> None:
    with pytest.raises(ValueError, match="provider cannot be blank"):
        GasolineMarketMetadata(
            provider=" ",
            geography=make_geography(),
        )


def test_market_metadata_rejects_invalid_geography() -> None:
    with pytest.raises(TypeError, match="GasolinePriceGeography"):
        GasolineMarketMetadata(
            provider="EIA",
            geography="region",  # type: ignore[arg-type]
        )


def test_market_metadata_rejects_naive_publication_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        GasolineMarketMetadata(
            provider="EIA",
            geography=make_geography(),
            published_at=datetime(2026, 10, 12, tzinfo=None),  # noqa: DTZ001
        )


def test_market_metadata_is_immutable() -> None:
    from dataclasses import FrozenInstanceError

    metadata = GasolineMarketMetadata(
        provider="EIA",
        geography=make_geography(),
    )

    with pytest.raises(FrozenInstanceError):
        metadata.provider = "Other"  # type: ignore[misc]
