"""M8 integration tests for transactional EIA PostgreSQL persistence.

These tests run only against the isolated local M8 PostgreSQL database.
They never download external data or contact production infrastructure.
"""

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import Engine, create_engine, make_url

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.persistence.schema import (
    eia_pricing_observations,
    eia_pricing_snapshots,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_quote_normalization import (
    normalize_eia_observations,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)
OBSERVED_ON = date(2026, 10, 5)


def make_snapshot(
    *,
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    observed_on: date = OBSERVED_ON,
    refreshed_at: datetime = REFRESHED_AT,
    price: str = "5.123",
) -> EiaPricingSnapshot:
    observations = tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=observed_on,
            price_per_gallon=Decimal(price),
        )
        for grade in GasolineGrade
    )

    return EiaPricingSnapshot(
        region=region,
        quotes=normalize_eia_observations(
            observations=observations,
            region=region,
        ),
        refreshed_at=refreshed_at,
    )


@pytest.fixture
def m8_engine() -> Iterator[Engine]:
    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.skip("M8 isolated PostgreSQL URL is not configured")

    url = make_url(raw_url)

    # Guard against accidentally modifying Neon or another database.
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.database == "routevalue_m8_eia_test"
    assert url.username == "routevalue_local"
    assert url.drivername == "postgresql+psycopg"

    engine = create_engine(url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()

            assert identity[0] == "routevalue_m8_eia_test"
            assert identity[1] == "routevalue_local"

        # This database was created specifically for these tests.
        # Clear only the two EIA pricing tables.
        with engine.begin() as connection:
            connection.execute(delete(eia_pricing_observations))
            connection.execute(delete(eia_pricing_snapshots))

        yield engine

    finally:
        with engine.begin() as connection:
            connection.execute(delete(eia_pricing_observations))
            connection.execute(delete(eia_pricing_snapshots))

        engine.dispose()


def test_new_repository_starts_empty(m8_engine: Engine) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    assert repository.get_snapshot(EIA_CALIFORNIA_REGION) is None


def test_first_snapshot_insert_and_roundtrip(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    original = make_snapshot()

    repository.save_snapshot(original)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.region == original.region
    assert restored.refreshed_at == original.refreshed_at
    assert len(restored.quotes) == 3

    for grade in GasolineGrade:
        actual = restored.quote_for_grade(grade)
        expected = original.quote_for_grade(grade)

        assert actual.price_per_gallon == expected.price_per_gallon
        assert actual.observed_at == expected.observed_at
        assert actual.fuel_grade is grade
        assert actual.source is expected.source
        assert actual.market_metadata == expected.market_metadata


def test_first_insert_creates_exactly_three_observations(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(make_snapshot())

    with m8_engine.connect() as connection:
        snapshot_count = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_snapshots")
        ).scalar_one()

        observation_count = connection.execute(
            text("SELECT COUNT(*) FROM public.eia_pricing_observations")
        ).scalar_one()

    assert snapshot_count == 1
    assert observation_count == 3


def test_identical_observation_can_be_refreshed(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(make_snapshot())

    newer = make_snapshot(refreshed_at=REFRESHED_AT + timedelta(hours=1))

    repository.save_snapshot(newer)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == newer.refreshed_at
    assert len(restored.quotes) == 3


def test_older_observation_is_rejected_without_data_loss(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    original = make_snapshot()
    repository.save_snapshot(original)

    older = make_snapshot(
        observed_on=date(2026, 9, 28),
        refreshed_at=REFRESHED_AT + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="observation date"):
        repository.save_snapshot(older)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at
    assert restored.quotes == original.quotes


def test_conflicting_same_date_price_rolls_back(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    original = make_snapshot()
    repository.save_snapshot(original)

    conflicting = make_snapshot(
        price="6.999",
        refreshed_at=REFRESHED_AT + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="conflicting EIA price"):
        repository.save_snapshot(conflicting)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at
    assert restored.quotes == original.quotes


def test_regressing_refresh_timestamp_is_rejected(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    original = make_snapshot()
    repository.save_snapshot(original)

    older = make_snapshot(refreshed_at=REFRESHED_AT - timedelta(hours=1))

    with pytest.raises(ValueError, match="refresh timestamp"):
        repository.save_snapshot(older)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at


def test_california_and_national_are_independent(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    california = make_snapshot(
        region=EIA_CALIFORNIA_REGION,
        price="6.227",
    )

    national = make_snapshot(
        region=EIA_US_REGION,
        price="4.354",
    )

    repository.save_snapshot(california)
    repository.save_snapshot(national)

    california_restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    national_restored = repository.get_snapshot(EIA_US_REGION)

    assert california_restored is not None
    assert national_restored is not None

    assert california_restored.quote_for_grade(GasolineGrade.REGULAR).price_per_gallon == Decimal(
        "6.227"
    )

    assert national_restored.quote_for_grade(GasolineGrade.REGULAR).price_per_gallon == Decimal(
        "4.354"
    )


def test_snapshot_survives_new_database_connection(
    m8_engine: Engine,
) -> None:
    first_repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    first_repository.save_snapshot(make_snapshot())

    # A new repository and independent connection must see persisted data.
    second_repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    restored = second_repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert len(restored.quotes) == 3
    assert restored.refreshed_at == REFRESHED_AT
