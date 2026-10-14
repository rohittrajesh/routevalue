"""Transactional PostgreSQL persistence for EIA gasoline snapshots."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Connection, Engine

from routevalue.domain.gasoline_price_metadata import (
    GasolineMarketMetadata,
)
from routevalue.domain.models import (
    GasolineGrade,
    GasolinePriceQuote,
    GasolinePriceSource,
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
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)

_SUPPORTED_REGIONS = (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
)


class EiaPricingPersistenceError(RuntimeError):
    """Persisted EIA pricing data violates a required invariant."""


def _require_region(region: EiaGasolineRegion) -> str:
    if not isinstance(region, EiaGasolineRegion):
        raise TypeError("region must be an EiaGasolineRegion")

    if region not in _SUPPORTED_REGIONS:
        raise ValueError("unsupported EIA pricing region")

    return region.geography.region_id


def _read_snapshot(
    connection: Connection,
    region: EiaGasolineRegion,
) -> EiaPricingSnapshot | None:
    region_id = _require_region(region)

    header = (
        connection.execute(
            select(eia_pricing_snapshots).where(eia_pricing_snapshots.c.region_id == region_id)
        )
        .mappings()
        .one_or_none()
    )

    if header is None:
        return None

    if (
        header["geographic_scope"] != region.geography.scope.value
        or header["display_name"] != region.geography.display_name
        or header["provider"] != "EIA"
        or header["workbook_url"] != region.workbook_url
    ):
        raise EiaPricingPersistenceError("stored EIA snapshot provenance mismatch")

    refreshed_at = header["refreshed_at"]

    if not isinstance(refreshed_at, datetime):
        raise EiaPricingPersistenceError("stored refresh timestamp is invalid")

    rows = (
        connection.execute(
            select(eia_pricing_observations).where(
                eia_pricing_observations.c.region_id == region_id
            )
        )
        .mappings()
        .all()
    )

    if len(rows) != len(GasolineGrade):
        raise EiaPricingPersistenceError("stored EIA snapshot is incomplete")

    quotes: list[GasolinePriceQuote] = []

    for row in rows:
        try:
            grade = GasolineGrade(row["fuel_grade"])
        except (ValueError, TypeError) as exc:
            raise EiaPricingPersistenceError("stored gasoline grade is invalid") from exc

        if row["series_id"] != region.series_for_grade(grade):
            raise EiaPricingPersistenceError("stored EIA series does not match grade")

        observed_at = row["observed_at"]
        price = row["price_per_gallon"]

        if not isinstance(observed_at, datetime):
            raise EiaPricingPersistenceError("stored observation time is invalid")

        if not isinstance(price, Decimal):
            raise EiaPricingPersistenceError("stored gasoline price is not Decimal")

        try:
            quote = GasolinePriceQuote(
                price_per_gallon=price,
                fuel_grade=grade,
                source=GasolinePriceSource.REGIONAL_MARKET,
                observed_at=observed_at,
                market_metadata=GasolineMarketMetadata(
                    provider="EIA",
                    geography=region.geography,
                ),
            )
        except (TypeError, ValueError) as exc:
            raise EiaPricingPersistenceError("stored EIA quote is invalid") from exc

        quotes.append(quote)

    try:
        return EiaPricingSnapshot(
            region=region,
            quotes=tuple(quotes),
            refreshed_at=refreshed_at,
        )
    except (TypeError, ValueError) as exc:
        raise EiaPricingPersistenceError("stored EIA snapshot is invalid") from exc


def _validate_replacement(
    previous: EiaPricingSnapshot,
    replacement: EiaPricingSnapshot,
) -> None:
    if replacement.refreshed_at < previous.refreshed_at:
        raise ValueError("refresh timestamp cannot regress")

    for grade in GasolineGrade:
        old = previous.quote_for_grade(grade)
        new = replacement.quote_for_grade(grade)

        if old.observed_at is None or new.observed_at is None:
            raise ValueError("snapshot observations require timestamps")

        if new.observed_at < old.observed_at:
            raise ValueError("EIA observation date cannot regress")

        if new.observed_at == old.observed_at and new.price_per_gallon != old.price_per_gallon:
            raise ValueError("conflicting EIA price for same observation date")


class PostgresEiaPricingSnapshotRepository:
    """Read and atomically replace validated regional EIA snapshots."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def get_snapshot(
        self,
        region: EiaGasolineRegion,
    ) -> EiaPricingSnapshot | None:
        """Read a complete snapshot without contacting EIA."""

        _require_region(region)

        with self._engine.connect() as connection:
            return _read_snapshot(connection, region)

    def save_snapshot(
        self,
        snapshot: EiaPricingSnapshot,
    ) -> None:
        """Atomically insert or replace a regional EIA pricing snapshot.

        First-time inserts are distinguished from existing records.
        Existing snapshots are validated under a PostgreSQL row lock.

        Failed writes roll back the entire transaction.
        """

        if not isinstance(snapshot, EiaPricingSnapshot):
            raise TypeError("snapshot must be an EiaPricingSnapshot")

        region = snapshot.region
        region_id = _require_region(region)

        with self._engine.begin() as connection:
            insert_header = (
                postgresql_insert(eia_pricing_snapshots)
                .values(
                    region_id=region_id,
                    geographic_scope=region.geography.scope.value,
                    display_name=region.geography.display_name,
                    provider="EIA",
                    workbook_url=region.workbook_url,
                    refreshed_at=snapshot.refreshed_at,
                )
                .on_conflict_do_nothing(index_elements=[eia_pricing_snapshots.c.region_id])
                .returning(eia_pricing_snapshots.c.region_id)
            )

            inserted_region = connection.execute(insert_header).scalar_one_or_none()

            connection.execute(
                select(eia_pricing_snapshots.c.region_id)
                .where(eia_pricing_snapshots.c.region_id == region_id)
                .with_for_update()
            ).scalar_one()

            if inserted_region is None:
                previous = _read_snapshot(connection, region)

                if previous is None:
                    raise EiaPricingPersistenceError("existing EIA snapshot header disappeared")

                _validate_replacement(previous, snapshot)

            connection.execute(
                delete(eia_pricing_observations).where(
                    eia_pricing_observations.c.region_id == region_id
                )
            )

            values: list[dict[str, object]] = []

            for grade in GasolineGrade:
                quote = snapshot.quote_for_grade(grade)

                if quote.observed_at is None:
                    raise ValueError("snapshot quote requires observed_at")

                values.append(
                    {
                        "region_id": region_id,
                        "fuel_grade": grade.value,
                        "series_id": region.series_for_grade(grade),
                        "observed_at": quote.observed_at,
                        "price_per_gallon": quote.price_per_gallon,
                    }
                )

            connection.execute(
                insert(eia_pricing_observations),
                values,
            )

            connection.execute(
                update(eia_pricing_snapshots)
                .where(eia_pricing_snapshots.c.region_id == region_id)
                .values(
                    geographic_scope=region.geography.scope.value,
                    display_name=region.geography.display_name,
                    provider="EIA",
                    workbook_url=region.workbook_url,
                    refreshed_at=snapshot.refreshed_at,
                )
            )
