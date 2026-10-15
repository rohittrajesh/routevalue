"""Read-only production EIA gasoline pricing dependencies."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from routevalue.application.gasoline_price_geography import (
    PricingJurisdictionResolver,
    PricingJurisdictionResult,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceLookupRequest,
    GasolinePriceProvider,
)
from routevalue.application.models import ResolvedLocation
from routevalue.domain.models import GasolinePriceQuote
from routevalue.infrastructure.persistence.eia_pricing_snapshots import (
    PostgresEiaPricingSnapshotRepository,
)
from routevalue.infrastructure.pricing.census_resolver_lifecycle import (
    get_census_pricing_jurisdiction_resolver,
)
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import (
    PostgresEiaGasolinePriceProvider,
)


def build_eia_pricing_dependencies(
    *,
    engine: Engine,
) -> tuple[GasolinePriceProvider, PricingJurisdictionResolver]:
    """Construct price and jurisdiction adapters using a caller-owned engine."""
    repository = PostgresEiaPricingSnapshotRepository(engine=engine)
    provider: GasolinePriceProvider = PostgresEiaGasolinePriceProvider(
        repository=repository,
    )
    resolver: PricingJurisdictionResolver = get_census_pricing_jurisdiction_resolver()
    return provider, resolver


@dataclass(frozen=True, slots=True)
class _DeferredEiaPriceProvider:
    engine_factory: Callable[[], Engine]

    def get_price(
        self,
        request: GasolinePriceLookupRequest,
    ) -> GasolinePriceQuote | None:
        engine = self.engine_factory()
        repository = PostgresEiaPricingSnapshotRepository(engine=engine)
        provider = PostgresEiaGasolinePriceProvider(repository=repository)
        return provider.get_price(request)


@dataclass(frozen=True, slots=True)
class _DeferredCensusResolver:
    def resolve(self, location: ResolvedLocation) -> PricingJurisdictionResult:
        resolver = get_census_pricing_jurisdiction_resolver()
        return resolver.resolve(location)


def build_lazy_eia_pricing_dependencies(
    *,
    engine_factory: Callable[[], Engine],
) -> tuple[GasolinePriceProvider, PricingJurisdictionResolver]:
    """Defer engine and Census initialization until an automatic lookup.

    In particular, legacy manual gasoline and BEV requests never need
    EIA-specific database initialization.
    """
    provider: GasolinePriceProvider = _DeferredEiaPriceProvider(
        engine_factory=engine_factory,
    )
    resolver: PricingJurisdictionResolver = _DeferredCensusResolver()
    return provider, resolver
