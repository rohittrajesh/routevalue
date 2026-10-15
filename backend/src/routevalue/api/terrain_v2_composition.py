"""Safe composition of authenticated terrain-aware V2 evaluation."""

from collections.abc import Callable
from datetime import UTC, datetime

from routevalue.api.terrain_v2_service import TerrainV2EvaluationService
from routevalue.application.authenticated_terrain_trip import (
    AuthenticatedTerrainTripService,
    AutomaticGasolinePriceResolver,
)
from routevalue.application.gasoline_price_geography import (
    PricingJurisdictionResolver,
)
from routevalue.application.gasoline_price_ports import (
    GasolinePriceProvider,
)
from routevalue.application.models import ResolvedLocation
from routevalue.application.ports import (
    RouteProvider,
    SavedVehicleRepository,
    UserPreferencesRepository,
)
from routevalue.application.profile_resolution import ProfileResolutionService
from routevalue.application.terrain_acquisition import TerrainAcquisitionService
from routevalue.domain.models import GasolineGrade, GasolinePriceQuote
from routevalue.infrastructure.pricing.eia_trip_price_resolution import (
    resolve_persisted_eia_gasoline_price,
)


def build_terrain_v2_evaluation_service(
    *,
    preferences_repository: UserPreferencesRepository,
    saved_vehicle_repository: SavedVehicleRepository,
    route_provider: RouteProvider,
    terrain_acquisition_service: TerrainAcquisitionService | None = None,
    gasoline_price_provider: GasolinePriceProvider | None = None,
    gasoline_jurisdiction_resolver: PricingJurisdictionResolver | None = None,
    pricing_clock: Callable[[], datetime] | None = None,
) -> TerrainV2EvaluationService:
    """Build the authenticated V2 evaluator with optional dependencies.

    Terrain acquisition remains disabled by default.

    Automatic gasoline pricing is available only when both the
    persisted-quote provider and trusted geographic resolver are
    explicitly configured.

    Merely constructing the service never retrieves EIA workbooks,
    queries the pricing provider, or accesses the database.

    Saved-vehicle ownership remains enforced by the existing
    profile-resolution service.
    """

    if (gasoline_price_provider is None) != (gasoline_jurisdiction_resolver is None):
        raise ValueError(
            "gasoline_price_provider and gasoline_jurisdiction_resolver must be configured together"
        )

    if pricing_clock is not None and (
        gasoline_price_provider is None or gasoline_jurisdiction_resolver is None
    ):
        raise ValueError("pricing_clock requires automatic gasoline pricing")

    automatic_resolver: AutomaticGasolinePriceResolver | None = None

    if gasoline_price_provider is not None and gasoline_jurisdiction_resolver is not None:
        provider = gasoline_price_provider
        jurisdiction_resolver = gasoline_jurisdiction_resolver
        clock = pricing_clock if pricing_clock is not None else (lambda: datetime.now(UTC))

        def resolve_automatic_price(
            origin: ResolvedLocation,
            fuel_grade: GasolineGrade,
        ) -> GasolinePriceQuote:
            as_of = clock()

            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("pricing clock must return a timezone-aware datetime")

            return resolve_persisted_eia_gasoline_price(
                provider=provider,
                jurisdiction_resolver=jurisdiction_resolver,
                origin=origin,
                fuel_grade=fuel_grade,
                as_of=as_of,
            )

        automatic_resolver = resolve_automatic_price

    profile_resolution_service = ProfileResolutionService(
        preferences_repository=preferences_repository,
        saved_vehicle_repository=saved_vehicle_repository,
    )

    application_service = AuthenticatedTerrainTripService(
        profile_resolution_service=profile_resolution_service,
        route_provider=route_provider,
        terrain_acquisition_service=terrain_acquisition_service,
        automatic_gasoline_price_resolver=automatic_resolver,
    )

    return TerrainV2EvaluationService(
        application_service=application_service,
    )
