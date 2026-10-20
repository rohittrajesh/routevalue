"""M8 PostgreSQL concurrency and snapshot-integrity integration tests.

Runs exclusively against the isolated local M8 database.
No external downloads or production connections are permitted.
"""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine, create_engine, make_url

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    EiaPricingPersistenceError,
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

REFRESH_TIME = datetime(2026, 10, 13, 15, tzinfo=UTC)
OBSERVATION_DATE = date(2026, 10, 5)


def make_snapshot(
    *,
    region: EiaGasolineRegion = EIA_CALIFORNIA_REGION,
    price: str = "5.123",
    observed_on: date = OBSERVATION_DATE,
    refreshed_at: datetime = REFRESH_TIME,
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
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.skip("Isolated M8 PostgreSQL URL not configured")

    url = make_url(raw_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "routevalue_local"
    assert url.database == "routevalue_m8_eia_test"

    test_engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    def clean() -> None:
        with test_engine.begin() as connection:
            connection.execute(delete(eia_pricing_observations))
            connection.execute(delete(eia_pricing_snapshots))

    try:
        with test_engine.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT current_database()").scalar_one()
                == "routevalue_m8_eia_test"
            )

            assert (
                connection.exec_driver_sql("SELECT current_user").scalar_one() == "routevalue_local"
            )

            assert (
                connection.exec_driver_sql(
                    "SELECT version_num FROM public.alembic_version"
                ).scalar_one()
                == "f2b7c39a106d"
            )

        clean()
        yield test_engine
    finally:
        try:
            clean()
        finally:
            test_engine.dispose()


def test_simultaneous_conflicting_first_writes(
    engine: Engine,
) -> None:
    """Only one competing same-date market observation may win."""

    barrier = Barrier(3)

    first = make_snapshot(price="5.123")
    second = make_snapshot(price="6.456")

    def attempt(snapshot: EiaPricingSnapshot) -> str:
        repository = PostgresEiaPricingSnapshotRepository(engine=engine)

        barrier.wait(timeout=10)

        try:
            repository.save_snapshot(snapshot)
        except ValueError as exc:
            assert "conflicting EIA price" in str(exc)
            return "rejected"

        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(attempt, first)
        second_future = executor.submit(attempt, second)

        barrier.wait(timeout=10)

        outcomes = [
            first_future.result(timeout=20),
            second_future.result(timeout=20),
        ]

    assert sorted(outcomes) == ["rejected", "saved"]

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)
    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert len(restored.quotes) == 3

    prices = {quote.price_per_gallon for quote in restored.quotes}

    assert prices in (
        {Decimal("5.123")},
        {Decimal("6.456")},
    )

    with engine.connect() as connection:
        rows = connection.execute(
            select(eia_pricing_observations).where(eia_pricing_observations.c.region_id == "SCA")
        ).all()

    assert len(rows) == 3


def test_concurrent_writes_to_different_regions(
    engine: Engine,
) -> None:
    """California and national snapshots must remain independent."""

    barrier = Barrier(3)

    california = make_snapshot(
        region=EIA_CALIFORNIA_REGION,
        price="6.227",
    )
    national = make_snapshot(
        region=EIA_US_REGION,
        price="4.354",
    )

    def save(snapshot: EiaPricingSnapshot) -> None:
        repository = PostgresEiaPricingSnapshotRepository(engine=engine)
        barrier.wait(timeout=10)
        repository.save_snapshot(snapshot)

    with ThreadPoolExecutor(max_workers=2) as executor:
        california_future = executor.submit(save, california)
        national_future = executor.submit(save, national)

        barrier.wait(timeout=10)

        california_future.result(timeout=20)
        national_future.result(timeout=20)

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)

    restored_california = repository.get_snapshot(EIA_CALIFORNIA_REGION)
    restored_national = repository.get_snapshot(EIA_US_REGION)

    assert restored_california is not None
    assert restored_national is not None

    assert restored_california.quote_for_grade(GasolineGrade.REGULAR).price_per_gallon == Decimal(
        "6.227"
    )

    assert restored_national.quote_for_grade(GasolineGrade.REGULAR).price_per_gallon == Decimal(
        "4.354"
    )


def test_incomplete_stored_snapshot_is_rejected(
    engine: Engine,
) -> None:
    """Missing grade rows must not silently become missing prices."""

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)

    repository.save_snapshot(make_snapshot())

    # Simulate corrupted stored data inside the isolated test database.
    with engine.begin() as connection:
        connection.execute(
            delete(eia_pricing_observations).where(
                eia_pricing_observations.c.region_id == "SCA",
                eia_pricing_observations.c.fuel_grade == "premium",
            )
        )

    with pytest.raises(
        EiaPricingPersistenceError,
        match="incomplete",
    ):
        repository.get_snapshot(EIA_CALIFORNIA_REGION)

    # The repository must also refuse replacing a corrupted snapshot.
    replacement = make_snapshot(
        observed_on=date(2026, 10, 12),
        refreshed_at=REFRESH_TIME + timedelta(days=1),
        price="6.123",
    )

    with pytest.raises(
        EiaPricingPersistenceError,
        match="incomplete",
    ):
        repository.save_snapshot(replacement)

    # The rejected transaction must not fabricate a missing row.
    with engine.connect() as connection:
        remaining = connection.execute(
            select(eia_pricing_observations).where(eia_pricing_observations.c.region_id == "SCA")
        ).all()

    assert len(remaining) == 2


def test_bad_series_mapping_is_rejected(
    engine: Engine,
) -> None:
    """Incorrect persisted EIA series IDs must not be trusted."""

    from sqlalchemy import update

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)
    repository.save_snapshot(make_snapshot())

    with engine.begin() as connection:
        connection.execute(
            update(eia_pricing_observations)
            .where(
                eia_pricing_observations.c.region_id == "SCA",
                eia_pricing_observations.c.fuel_grade == "premium",
            )
            .values(series_id="INCORRECT_SERIES")
        )

    with pytest.raises(
        EiaPricingPersistenceError,
        match="series",
    ):
        repository.get_snapshot(EIA_CALIFORNIA_REGION)


def test_rejected_update_preserves_all_original_rows(
    engine: Engine,
) -> None:
    """A failed update cannot change the snapshot or its three grades."""

    repository = PostgresEiaPricingSnapshotRepository(engine=engine)

    original = make_snapshot()
    repository.save_snapshot(original)

    conflicting = make_snapshot(
        price="9.999",
        refreshed_at=REFRESH_TIME + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="conflicting"):
        repository.save_snapshot(conflicting)

    restored = repository.get_snapshot(EIA_CALIFORNIA_REGION)

    assert restored is not None
    assert restored.refreshed_at == original.refreshed_at
    assert restored.quotes == original.quotes

    with engine.connect() as connection:
        rows = connection.execute(
            select(eia_pricing_observations).where(eia_pricing_observations.c.region_id == "SCA")
        ).all()

    assert len(rows) == 3
