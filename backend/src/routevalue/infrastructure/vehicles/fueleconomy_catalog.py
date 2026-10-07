"""FuelEconomy.gov hierarchical vehicle-catalog integration."""

from dataclasses import dataclass
from xml.etree.ElementTree import Element

from routevalue.application.models import VehicleCatalogConfiguration
from routevalue.infrastructure.vehicles.fueleconomy_gov import (
    FuelEconomyGovClient,
    FuelEconomyGovResponseError,
)

FUEL_ECONOMY_SOURCE = "fueleconomy_gov"

_FUEL_ECONOMY_YEAR_PATH = "vehicle/menu/year"
_FUEL_ECONOMY_MAKE_PATH = "vehicle/menu/make"
_FUEL_ECONOMY_MODEL_PATH = "vehicle/menu/model"
_FUEL_ECONOMY_OPTIONS_PATH = "vehicle/menu/options"


@dataclass(frozen=True, slots=True)
class _FuelEconomyMenuItem:
    """One provider-specific FuelEconomy.gov menu item."""

    text: str
    value: str


class FuelEconomyGovCatalog:
    """Discover FuelEconomy.gov vehicles through its hierarchical catalog."""

    def __init__(
        self,
        *,
        client: FuelEconomyGovClient,
    ) -> None:
        self._client = client

    def list_years(self) -> tuple[int, ...]:
        """Return available model years newest first."""

        root = self._client.get_xml(_FUEL_ECONOMY_YEAR_PATH)
        items = _parse_menu_items(root)

        years: set[int] = set()

        for item in items:
            try:
                year = int(item.value)
            except ValueError as exc:
                raise FuelEconomyGovResponseError(
                    "FuelEconomy.gov returned an invalid model year"
                ) from exc

            if year <= 0:
                raise FuelEconomyGovResponseError("FuelEconomy.gov returned an invalid model year")

            years.add(year)

        return tuple(sorted(years, reverse=True))

    def list_makes(
        self,
        *,
        year: int,
    ) -> tuple[str, ...]:
        """Return makes for a model year in deterministic order."""

        _validate_year(year)

        root = self._client.get_xml(
            _FUEL_ECONOMY_MAKE_PATH,
            params={
                "year": str(year),
            },
        )

        return _sorted_unique_menu_values(_parse_menu_items(root))

    def list_models(
        self,
        *,
        year: int,
        make: str,
    ) -> tuple[str, ...]:
        """Return models for a year and make in deterministic order."""

        _validate_year(year)
        normalized_make = _require_nonblank(
            make,
            field_name="make",
        )

        root = self._client.get_xml(
            _FUEL_ECONOMY_MODEL_PATH,
            params={
                "year": str(year),
                "make": normalized_make,
            },
        )

        return _sorted_unique_menu_values(_parse_menu_items(root))

    def list_configurations(
        self,
        *,
        year: int,
        make: str,
        model: str,
    ) -> tuple[VehicleCatalogConfiguration, ...]:
        """Return selectable configurations with provider provenance."""

        _validate_year(year)
        normalized_make = _require_nonblank(
            make,
            field_name="make",
        )
        normalized_model = _require_nonblank(
            model,
            field_name="model",
        )

        root = self._client.get_xml(
            _FUEL_ECONOMY_OPTIONS_PATH,
            params={
                "year": str(year),
                "make": normalized_make,
                "model": normalized_model,
            },
        )

        items = _parse_menu_items(root)

        configurations = tuple(
            VehicleCatalogConfiguration(
                year=year,
                make=normalized_make,
                model=normalized_model,
                configuration=item.text,
                source=FUEL_ECONOMY_SOURCE,
                source_id=item.value,
            )
            for item in items
        )

        return tuple(
            sorted(
                configurations,
                key=lambda configuration: (
                    configuration.configuration.casefold(),
                    configuration.configuration,
                    configuration.source_id,
                ),
            )
        )


def _parse_menu_items(
    root: Element,
) -> tuple[_FuelEconomyMenuItem, ...]:
    """Parse FuelEconomy.gov menu XML into validated provider items."""

    if root.tag != "menuItems":
        raise FuelEconomyGovResponseError(
            "FuelEconomy.gov menu response has an invalid root element"
        )

    items: list[_FuelEconomyMenuItem] = []

    for element in root.findall("./menuItem"):
        text = element.findtext("text")
        value = element.findtext("value")

        if text is None or not text.strip():
            raise FuelEconomyGovResponseError("FuelEconomy.gov menu item is missing text")

        if value is None or not value.strip():
            raise FuelEconomyGovResponseError("FuelEconomy.gov menu item is missing value")

        items.append(
            _FuelEconomyMenuItem(
                text=text.strip(),
                value=value.strip(),
            )
        )

    return tuple(items)


def _sorted_unique_menu_values(
    items: tuple[_FuelEconomyMenuItem, ...],
) -> tuple[str, ...]:
    """Return unique provider values in deterministic case-insensitive order."""

    values = {item.value for item in items}

    return tuple(
        sorted(
            values,
            key=lambda value: (
                value.casefold(),
                value,
            ),
        )
    )


def _validate_year(year: int) -> None:
    """Reject invalid catalog years before making a provider request."""

    if year <= 0:
        raise ValueError("year must be greater than zero")


def _require_nonblank(
    value: str,
    *,
    field_name: str,
) -> str:
    """Normalize and validate one catalog selection string."""

    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")

    return normalized
