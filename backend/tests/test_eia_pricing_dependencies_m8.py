"""M8-R2-E tests for production EIA pricing dependency composition."""

from unittest.mock import Mock, patch

from sqlalchemy.engine import Engine

from routevalue.api.eia_pricing_dependencies import (
    build_eia_pricing_dependencies,
)
from routevalue.infrastructure.pricing.census_jurisdiction import (
    CensusPricingJurisdictionResolver,
)
from routevalue.infrastructure.pricing.eia_snapshot_price_provider import (
    PostgresEiaGasolinePriceProvider,
)


def test_production_pricing_dependencies_are_composed() -> None:
    engine = Mock(spec=Engine)
    resolver = Mock(spec=CensusPricingJurisdictionResolver)

    with patch(
        "routevalue.api.eia_pricing_dependencies.get_census_pricing_jurisdiction_resolver",
        return_value=resolver,
    ) as get_resolver:
        provider, jurisdiction = build_eia_pricing_dependencies(
            engine=engine,
        )

    assert isinstance(provider, PostgresEiaGasolinePriceProvider)
    assert jurisdiction is resolver
    get_resolver.assert_called_once_with()


def test_composition_never_opens_a_database_connection() -> None:
    engine = Mock(spec=Engine)
    resolver = Mock(spec=CensusPricingJurisdictionResolver)

    with patch(
        "routevalue.api.eia_pricing_dependencies.get_census_pricing_jurisdiction_resolver",
        return_value=resolver,
    ):
        build_eia_pricing_dependencies(engine=engine)

    engine.connect.assert_not_called()
    engine.begin.assert_not_called()
    engine.dispose.assert_not_called()
