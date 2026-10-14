"""M8 tests for controlled EIA gasoline refresh orchestration.

All workbook downloads and persistence operations are mocked.
No network calls or database connections are performed.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from routevalue.domain.models import GasolineGrade
from routevalue.infrastructure.pricing import (
    eia_refresh_coordinator as coordinator_module,
)
from routevalue.infrastructure.pricing.eia_geography import (
    EIA_CALIFORNIA_REGION,
    EIA_US_REGION,
    EiaGasolineRegion,
)
from routevalue.infrastructure.pricing.eia_refresh_coordinator import (
    EiaRefreshCoordinator,
)
from routevalue.infrastructure.pricing.eia_refresh_models import (
    EiaRefreshFailureReason,
    EiaRefreshStatus,
)
from routevalue.infrastructure.pricing.eia_snapshot_cache import (
    EiaPricingSnapshot,
)
from routevalue.infrastructure.pricing.eia_xls_models import (
    EiaGasolineObservation,
)

REFRESHED_AT = datetime(2026, 10, 13, 15, tzinfo=UTC)
OBSERVED_ON = date(2026, 10, 5)
WORKBOOK_BYTES = b"mocked-eia-workbook"


class FakeSnapshotRepository:
    """Records persistence attempts without connecting to a database."""

    def __init__(
        self,
        error: Exception | None = None,
    ) -> None:
        self.saved: list[EiaPricingSnapshot] = []
        self.attempts = 0
        self.error = error

    def save_snapshot(
        self,
        snapshot: EiaPricingSnapshot,
    ) -> None:
        self.attempts += 1

        if self.error is not None:
            raise self.error

        self.saved.append(snapshot)


def make_observations(
    region: EiaGasolineRegion,
) -> tuple[EiaGasolineObservation, ...]:
    """Create three valid EIA observations for a supported region."""

    return tuple(
        EiaGasolineObservation(
            series_id=region.series_for_grade(grade),
            fuel_grade=grade,
            observed_on=OBSERVED_ON,
            price_per_gallon=Decimal("5.123"),
        )
        for grade in GasolineGrade
    )


def install_mock_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace only the XLS parsing I/O boundary."""

    def fake_parser(
        *,
        workbook_bytes: bytes,
        region: EiaGasolineRegion,
    ) -> tuple[EiaGasolineObservation, ...]:
        assert workbook_bytes == WORKBOOK_BYTES
        return make_observations(region)

    monkeypatch.setattr(
        coordinator_module,
        "parse_eia_xls_workbook",
        fake_parser,
    )


def make_coordinator(
    repository: FakeSnapshotRepository,
) -> EiaRefreshCoordinator:
    return EiaRefreshCoordinator(
        fetch_workbook=lambda region: WORKBOOK_BYTES,
        repository=repository,
        clock=lambda: REFRESHED_AT,
    )


@pytest.mark.parametrize(
    "region",
    [
        EIA_CALIFORNIA_REGION,
        EIA_US_REGION,
    ],
)
def test_successful_refresh_persists_complete_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    region: EiaGasolineRegion,
) -> None:
    install_mock_parser(monkeypatch)

    repository = FakeSnapshotRepository()
    coordinator = make_coordinator(repository)

    result = coordinator.refresh(region)

    assert result.status is EiaRefreshStatus.SUCCEEDED
    assert result.succeeded is True
    assert result.failure_reason is None
    assert result.refreshed_at == REFRESHED_AT

    assert repository.attempts == 1
    assert len(repository.saved) == 1

    snapshot = repository.saved[0]

    assert snapshot.region == region
    assert snapshot.refreshed_at == REFRESHED_AT
    assert len(snapshot.quotes) == 3

    for grade in GasolineGrade:
        quote = snapshot.quote_for_grade(grade)
        assert quote.fuel_grade is grade
        assert quote.price_per_gallon == Decimal("5.123")
        assert quote.observed_at is not None
        assert quote.market_metadata is not None
        assert quote.market_metadata.geography == region.geography


def test_download_failure_prevents_persistence() -> None:
    repository = FakeSnapshotRepository()

    def failing_download(region: EiaGasolineRegion) -> bytes:
        raise httpx.ConnectError("Simulated EIA connection failure")

    coordinator = EiaRefreshCoordinator(
        fetch_workbook=failing_download,
        repository=repository,
        clock=lambda: REFRESHED_AT,
    )

    result = coordinator.refresh(EIA_US_REGION)

    assert result.status is EiaRefreshStatus.FAILED
    assert result.failure_reason is (EiaRefreshFailureReason.DOWNLOAD_FAILED)
    assert result.refreshed_at is None
    assert repository.attempts == 0


def test_parser_failure_prevents_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeSnapshotRepository()

    def failing_parser(
        *,
        workbook_bytes: bytes,
        region: EiaGasolineRegion,
    ) -> tuple[EiaGasolineObservation, ...]:
        raise ValueError("Invalid XLS workbook")

    monkeypatch.setattr(
        coordinator_module,
        "parse_eia_xls_workbook",
        failing_parser,
    )

    result = make_coordinator(repository).refresh(EIA_US_REGION)

    assert result.failure_reason is (EiaRefreshFailureReason.PARSE_FAILED)
    assert repository.attempts == 0


def test_normalization_failure_prevents_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)
    repository = FakeSnapshotRepository()

    def failing_normalizer(
        *,
        observations: tuple[EiaGasolineObservation, ...],
        region: EiaGasolineRegion,
    ) -> tuple[()]:
        raise ValueError("Invalid gasoline observations")

    monkeypatch.setattr(
        coordinator_module,
        "normalize_eia_observations",
        failing_normalizer,
    )

    result = make_coordinator(repository).refresh(EIA_CALIFORNIA_REGION)

    assert result.failure_reason is (EiaRefreshFailureReason.NORMALIZATION_FAILED)
    assert repository.attempts == 0


def test_invalid_snapshot_prevents_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)
    repository = FakeSnapshotRepository()

    def incomplete_normalizer(
        *,
        observations: tuple[EiaGasolineObservation, ...],
        region: EiaGasolineRegion,
    ) -> tuple[()]:
        return ()

    monkeypatch.setattr(
        coordinator_module,
        "normalize_eia_observations",
        incomplete_normalizer,
    )

    result = make_coordinator(repository).refresh(EIA_CALIFORNIA_REGION)

    assert result.failure_reason is (EiaRefreshFailureReason.SNAPSHOT_INVALID)
    assert repository.attempts == 0


def test_database_failure_is_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)

    database_error = OperationalError(
        "INSERT INTO eia_pricing_snapshots",
        {},
        Exception("Simulated database outage"),
    )

    repository = FakeSnapshotRepository(error=database_error)

    result = make_coordinator(repository).refresh(EIA_US_REGION)

    assert result.status is EiaRefreshStatus.FAILED
    assert result.failure_reason is (EiaRefreshFailureReason.PERSISTENCE_FAILED)
    assert repository.attempts == 1
    assert repository.saved == []


def test_conflicting_observation_is_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)

    repository = FakeSnapshotRepository(
        error=ValueError("conflicting EIA price for same observation date")
    )

    result = make_coordinator(repository).refresh(EIA_CALIFORNIA_REGION)

    assert result.failure_reason is (EiaRefreshFailureReason.CONFLICT)
    assert repository.attempts == 1
    assert repository.saved == []


def test_unexpected_programming_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)

    repository = FakeSnapshotRepository(error=RuntimeError("Unexpected implementation failure"))

    with pytest.raises(
        RuntimeError,
        match="Unexpected implementation failure",
    ):
        make_coordinator(repository).refresh(EIA_US_REGION)

    assert repository.attempts == 1
    assert repository.saved == []


def test_invalid_region_is_rejected_before_download() -> None:
    repository = FakeSnapshotRepository()
    coordinator = make_coordinator(repository)

    with pytest.raises(TypeError, match="EiaGasolineRegion"):
        coordinator.refresh(cast(EiaGasolineRegion, "California"))

    assert repository.attempts == 0


def test_naive_clock_is_rejected_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_parser(monkeypatch)

    repository = FakeSnapshotRepository()

    coordinator = EiaRefreshCoordinator(
        fetch_workbook=lambda region: WORKBOOK_BYTES,
        repository=repository,
        clock=lambda: REFRESHED_AT.replace(tzinfo=None),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        coordinator.refresh(EIA_US_REGION)

    assert repository.attempts == 0


def test_invalid_workbook_fetcher_result_propagates() -> None:
    repository = FakeSnapshotRepository()

    coordinator = EiaRefreshCoordinator(
        fetch_workbook=lambda region: cast(bytes, "not bytes"),
        repository=repository,
        clock=lambda: REFRESHED_AT,
    )

    with pytest.raises(TypeError, match="must return bytes"):
        coordinator.refresh(EIA_US_REGION)

    assert repository.attempts == 0
