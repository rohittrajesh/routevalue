"""FuelEconomy.gov VehicleSpecificationProvider implementation."""

from xml.etree.ElementTree import Element

from routevalue.application.models import (
    VehicleCatalogConfiguration,
    VehicleSpecificationLookupResult,
    VehicleSpecificationUnavailableReason,
)
from routevalue.infrastructure.vehicles.fueleconomy_catalog import (
    FUEL_ECONOMY_SOURCE,
    FuelEconomyGovCatalog,
)
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovClient,
    FuelEconomyGovHTTPError,
    FuelEconomyGovResponseError,
)
from routevalue.infrastructure.vehicles.fueleconomy_specifications import (
    normalize_fueleconomy_vehicle,
)


class FuelEconomyGovVehicleSpecificationProvider:
    """Provide normalized vehicle catalog data and specifications."""

    def __init__(
        self,
        *,
        client: FuelEconomyGovClient,
    ) -> None:
        self._client = client
        self._catalog = FuelEconomyGovCatalog(
            client=client,
        )

    def list_years(self) -> tuple[int, ...]:
        """Return available FuelEconomy.gov model years."""

        return self._catalog.list_years()

    def list_makes(
        self,
        *,
        year: int,
    ) -> tuple[str, ...]:
        """Return makes for a model year."""

        return self._catalog.list_makes(
            year=year,
        )

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> tuple[str, ...]:
        """Return models for a year and make."""

        return self._catalog.list_models(
            year=year,
            make=make,
        )

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> tuple[VehicleCatalogConfiguration, ...]:
        """Return selectable configurations with FuelEconomy.gov provenance."""

        return self._catalog.list_configurations(
            year=year,
            make=make,
            model=model,
        )

    def get_specification(
        self,
        configuration: VehicleCatalogConfiguration,
    ) -> VehicleSpecificationLookupResult:
        """Resolve one FuelEconomy.gov configuration into a normalized specification."""

        if configuration.source != FUEL_ECONOMY_SOURCE:
            raise ValueError("configuration source must match FuelEconomy.gov")

        if not _is_valid_vehicle_id(configuration.source_id):
            return _not_found()

        try:
            root = self._client.get_xml(f"vehicle/{configuration.source_id}")
        except FuelEconomyGovHTTPError as exc:
            if exc.status_code == 404:
                return _not_found()

            raise

        _validate_vehicle_identity(
            root,
            requested_vehicle_id=configuration.source_id,
        )

        return normalize_fueleconomy_vehicle(root)


def _is_valid_vehicle_id(
    vehicle_id: str,
) -> bool:
    """Return whether a provider ID has the documented numeric vehicle-ID shape."""

    return vehicle_id.isascii() and vehicle_id.isdigit() and int(vehicle_id) > 0


def _validate_vehicle_identity(
    root: Element,
    *,
    requested_vehicle_id: str,
) -> None:
    """Ensure a fetched vehicle record identifies the requested provider vehicle."""

    if root.tag != "vehicle":
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov vehicle response has an invalid root element"
        )

    response_vehicle_id = root.findtext("id")

    if response_vehicle_id is None or not response_vehicle_id.strip():
        raise FuelEconomyGovResponseError("FuelEconomy.gov vehicle response is missing vehicle id")

    if response_vehicle_id.strip() != requested_vehicle_id:
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov vehicle response id does not match requested vehicle"
        )


def _not_found() -> VehicleSpecificationLookupResult:
    """Build the provider-neutral vehicle-not-found outcome."""

    return VehicleSpecificationLookupResult(
        specification=None,
        unavailable_reason=VehicleSpecificationUnavailableReason.NOT_FOUND,
    )
