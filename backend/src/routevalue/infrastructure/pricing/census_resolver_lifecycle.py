"""Process-local lifecycle for the offline Census jurisdiction resolver."""

from functools import lru_cache

from routevalue.infrastructure.pricing.census_jurisdiction import (
    CensusPricingJurisdictionResolver,
)


@lru_cache(maxsize=1)
def get_census_pricing_jurisdiction_resolver() -> CensusPricingJurisdictionResolver:
    """Return a reusable Census resolver within the current process.

    The packaged boundaries are loaded lazily on the first call.
    Subsequent calls reuse the same resolver and parsed geometries.

    This function performs no network requests.
    """
    return CensusPricingJurisdictionResolver()
