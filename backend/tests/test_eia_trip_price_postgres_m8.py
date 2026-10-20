"""M8 read-only automatic gasoline pricing PostgreSQL integration tests."""

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import Engine, create_engine, make_url

from routevalue.application.gasoline_price_failures import (
    GasolinePriceUnavailableError,
    GasolinePriceUnavailableReason,
)
from routevalue.application.gasoline_price_geography import (
    PricingJurisdiction,
    PricingJurisdictionResult,
)
from routevalue.application.models import ResolvedLocation
from routevalue.domain.models import GasolineGrade, GasolinePriceQuote
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
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import (
    PostgresEiaGasolinePriceProvider,
)
from routevalue.infrastructure.pricing.eia_trip_price_resolution import (
    resolve_persisted_eia_gasoline_price,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

AS_OF = datetime(2026, 10, 14, 12, tzinfo=UTC)
REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)

ORIGIN = ResolvedLocation(
    display_name="Integration test origin",
    latitude=34.0,
    longitude=-118.0,
)


class FakeJurisdictionResolver:
    def __init__(self, jurisdiction: PricingJurisdiction) -> None:
        self.jurisdiction = jurisdiction
        self.calls: list[ResolvedLocation] = []

    def resolve(
        self,
        location: ResolvedLocation,
    ) -> PricingJurisdictionResult:
        self.calls.append(location)
        return PricingJurisdictionResult(jurisdiction=self.jurisdiction)


@pytest.fixture
def m8_engine() -> Iterator[Engine]:
    raw_url = os.environ.get("DATABASE_URL_UNPOOLED")

    if not raw_url:
        pytest.skip("M8 isolated PostgreSQL URL is not configured")

    url = make_url(raw_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "routevalue_local"
    assert url.database == "routevalue_m8_eia_test"

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    def clean() -> None:
        with engine.begin() as connection:
            connection.execute(delete(eia_pricing_observations))
            connection.execute(delete(eia_pricing_snapshots))

    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()

            assert identity[0] == "routevalue_m8_eia_test"
            assert identity[1] == "routevalue_local"

            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()

            assert revision == "d41e7a902b63"

        clean()
        yield engine

    finally:
        try:
            clean()
        finally:
            engine.dispose()


def make_snapshot(
    *,
    region: EiaGasolineRegion,
    price: str,
    observed_on: date = date(2026, 10, 12),
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
        refreshed_at=REFRESHED_AT,
    )


def make_provider(
    engine: Engine,
) -> PostgresEiaGasolinePriceProvider:
    return PostgresEiaGasolinePriceProvider(
        repository=PostgresEiaPricingSnapshotRepository(engine=engine)
    )


def resolve(
    *,
    engine: Engine,
    jurisdiction: PricingJurisdiction,
    grade: GasolineGrade = GasolineGrade.REGULAR,
) -> GasolinePriceQuote:
    return resolve_persisted_eia_gasoline_price(
        provider=make_provider(engine),
        jurisdiction_resolver=FakeJurisdictionResolver(jurisdiction),
        origin=ORIGIN,
        fuel_grade=grade,
        as_of=AS_OF,
    )


def test_california_uses_persisted_state_price(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(
        make_snapshot(
            region=EIA_CALIFORNIA_REGION,
            price="6.227",
        )
    )
    repository.save_snapshot(
        make_snapshot(
            region=EIA_US_REGION,
            price="4.354",
        )
    )

    quote = resolve(
        engine=m8_engine,
        jurisdiction=PricingJurisdiction.CALIFORNIA,
    )

    assert quote.price_per_gallon == Decimal("6.227")
    assert quote.fuel_grade is GasolineGrade.REGULAR
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_CALIFORNIA_REGION.geography


def test_california_falls_back_to_persisted_national_price(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(
        make_snapshot(
            region=EIA_US_REGION,
            price="4.354",
        )
    )

    quote = resolve(
        engine=m8_engine,
        jurisdiction=PricingJurisdiction.CALIFORNIA,
        grade=GasolineGrade.PREMIUM,
    )

    assert quote.price_per_gallon == Decimal("4.354")
    assert quote.fuel_grade is GasolineGrade.PREMIUM
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_US_REGION.geography


def test_other_us_uses_national_not_california(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(
        make_snapshot(
            region=EIA_CALIFORNIA_REGION,
            price="6.227",
        )
    )
    repository.save_snapshot(
        make_snapshot(
            region=EIA_US_REGION,
            price="4.354",
        )
    )

    quote = resolve(
        engine=m8_engine,
        jurisdiction=PricingJurisdiction.OTHER_US,
        grade=GasolineGrade.MIDGRADE,
    )

    assert quote.price_per_gallon == Decimal("4.354")
    assert quote.fuel_grade is GasolineGrade.MIDGRADE
    assert quote.market_metadata is not None
    assert quote.market_metadata.geography == EIA_US_REGION.geography


def test_stale_stored_quotes_are_rejected(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(
        make_snapshot(
            region=EIA_CALIFORNIA_REGION,
            price="6.227",
            observed_on=date(2026, 9, 28),
        )
    )
    repository.save_snapshot(
        make_snapshot(
            region=EIA_US_REGION,
            price="4.354",
            observed_on=date(2026, 9, 28),
        )
    )

    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(
            engine=m8_engine,
            jurisdiction=PricingJurisdiction.CALIFORNIA,
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_STALE


def test_missing_stored_quotes_are_explicitly_unavailable(
    m8_engine: Engine,
) -> None:
    with pytest.raises(GasolinePriceUnavailableError) as exc:
        resolve(
            engine=m8_engine,
            jurisdiction=PricingJurisdiction.OTHER_US,
        )

    assert exc.value.reason is GasolinePriceUnavailableReason.PRICE_NOT_FOUND


def test_read_only_lookup_preserves_database_rows(
    m8_engine: Engine,
) -> None:
    repository = PostgresEiaPricingSnapshotRepository(engine=m8_engine)

    repository.save_snapshot(
        make_snapshot(
            region=EIA_US_REGION,
            price="4.354",
        )
    )

    def row_counts() -> tuple[int, int]:
        with m8_engine.connect() as connection:
            snapshots = connection.execute(
                text("SELECT COUNT(*) FROM public.eia_pricing_snapshots")
            ).scalar_one()

            observations = connection.execute(
                text("SELECT COUNT(*) FROM public.eia_pricing_observations")
            ).scalar_one()

        return snapshots, observations

    before = row_counts()
    assert before == (1, 3)

    quote = resolve(
        engine=m8_engine,
        jurisdiction=PricingJurisdiction.OTHER_US,
    )

    after = row_counts()

    assert quote.price_per_gallon == Decimal("4.354")
    assert after == before
