from datetime import UTC, datetime, timedelta
from decimal import Decimal

from routevalue.domain.decision_engine import decide_route
from routevalue.domain.fuel_price import resolve_fuel_price_quote
from routevalue.domain.gasoline_energy import (
    estimate_gasoline_energy_if_available,
)
from routevalue.domain.models import (
    DecisionCandidate,
    DecisionReason,
    FuelPriceQuote,
    FuelPriceSource,
    GasolineGrade,
    GasolineVehicleProfile,
    RouteCandidate,
)


def test_user_override_flows_through_to_gasoline_energy_estimate() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    route = RouteCandidate(
        distance_meters=1_609_344,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )

    override = FuelPriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )
    local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=1),
    )

    resolved_price = resolve_fuel_price_quote(
        fuel_grade=vehicle.fuel_grade,
        as_of=as_of,
        user_override=override,
        local_market_quote=local,
    )

    estimate = estimate_gasoline_energy_if_available(
        route,
        vehicle=vehicle,
        fuel_price_quote=resolved_price,
    )

    assert resolved_price is override
    assert estimate is not None
    assert estimate.cost == Decimal("160.00")


def test_stale_local_price_falls_back_to_regional_for_energy_estimate() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    route = RouteCandidate(
        distance_meters=1_609_344,
        duration_seconds=3_600,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )

    stale_local = FuelPriceQuote(
        price_per_gallon=Decimal("4.50"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.LOCAL_MARKET,
        observed_at=as_of - timedelta(hours=49),
    )
    regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.20"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=1),
    )

    resolved_price = resolve_fuel_price_quote(
        fuel_grade=vehicle.fuel_grade,
        as_of=as_of,
        local_market_quote=stale_local,
        regional_market_quote=regional,
    )

    estimate = estimate_gasoline_energy_if_available(
        route,
        vehicle=vehicle,
        fuel_price_quote=resolved_price,
    )

    assert resolved_price is regional
    assert estimate is not None
    assert estimate.cost == Decimal("168.00")


def test_unavailable_fuel_price_produces_no_energy_estimate() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    route = RouteCandidate(
        distance_meters=10_000,
        duration_seconds=900,
        toll_cost=Decimal(0),
    )
    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(30),
        fuel_grade=GasolineGrade.REGULAR,
    )

    stale_regional = FuelPriceQuote(
        price_per_gallon=Decimal("4.20"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.REGIONAL_MARKET,
        observed_at=as_of - timedelta(days=8),
    )

    resolved_price = resolve_fuel_price_quote(
        fuel_grade=vehicle.fuel_grade,
        as_of=as_of,
        regional_market_quote=stale_regional,
    )

    estimate = estimate_gasoline_energy_if_available(
        route,
        vehicle=vehicle,
        fuel_price_quote=resolved_price,
    )

    assert resolved_price is None
    assert estimate is None


def test_gasoline_estimates_flow_into_route_decision_engine() -> None:
    as_of = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    vehicle = GasolineVehicleProfile(
        fuel_efficiency_mpg=Decimal(25),
        fuel_grade=GasolineGrade.REGULAR,
    )
    fuel_price = FuelPriceQuote(
        price_per_gallon=Decimal("4.00"),
        fuel_grade=GasolineGrade.REGULAR,
        source=FuelPriceSource.USER_OVERRIDE,
        observed_at=None,
    )

    resolved_price = resolve_fuel_price_quote(
        fuel_grade=vehicle.fuel_grade,
        as_of=as_of,
        user_override=fuel_price,
    )

    shorter_route = RouteCandidate(
        distance_meters=16_093,
        duration_seconds=1_700,
        toll_cost=Decimal(0),
    )
    longer_route = RouteCandidate(
        distance_meters=32_187,
        duration_seconds=1_800,
        toll_cost=Decimal(0),
    )

    shorter_energy = estimate_gasoline_energy_if_available(
        shorter_route,
        vehicle=vehicle,
        fuel_price_quote=resolved_price,
    )
    longer_energy = estimate_gasoline_energy_if_available(
        longer_route,
        vehicle=vehicle,
        fuel_price_quote=resolved_price,
    )

    assert shorter_energy is not None
    assert longer_energy is not None

    result = decide_route(
        [
            DecisionCandidate(
                route=shorter_route,
                energy_estimate=shorter_energy,
            ),
            DecisionCandidate(
                route=longer_route,
                energy_estimate=longer_energy,
            ),
        ],
        value_of_time_per_hour=Decimal(20),
        candidate_count=2,
        missing_data_present=False,
    )

    assert result.recommended_route is shorter_route
    assert result.reason is DecisionReason.FASTER_AND_CHEAPER
