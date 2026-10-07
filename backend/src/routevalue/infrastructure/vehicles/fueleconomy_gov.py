"""FuelEconomy.gov HTTP/XML infrastructure foundation."""

from collections.abc import Callable, Mapping
from time import sleep
from xml.etree.ElementTree import Element, ParseError, fromstring

import httpx

FUEL_ECONOMY_BASE_URL = "https://www.fueleconomy.gov/ws/rest"

FUEL_ECONOMY_TIMEOUT_SECONDS = 10.0

_FUEL_ECONOMY_MAX_ATTEMPTS = 3

_FUEL_ECONOMY_RETRY_DELAYS_SECONDS = (
    0.25,
    0.5,
)


class FuelEconomyGovError(RuntimeError):
    """Base error for FuelEconomy.gov infrastructure failures."""


class FuelEconomyGovTransportError(FuelEconomyGovError):
    """Raised when a request cannot successfully reach FuelEconomy.gov."""


class FuelEconomyGovHTTPError(FuelEconomyGovError):
    """Raised when FuelEconomy.gov returns a non-success HTTP response."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"FuelEconomy.gov returned HTTP {status_code}")


class FuelEconomyGovResponseError(FuelEconomyGovError):
    """Raised when a successful response cannot be safely parsed."""


class FuelEconomyGovClient:
    """Execute FuelEconomy.gov requests and return parsed XML responses."""

    def __init__(
        self,
        *,
        client: httpx.Client,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._client = client
        self._sleeper = sleeper

    def get_xml(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> Element:
        """GET one FuelEconomy.gov resource and parse its XML response."""

        normalized_path = path.strip()

        if not normalized_path:
            raise ValueError("path cannot be blank")

        url = f"{FUEL_ECONOMY_BASE_URL}/{normalized_path.lstrip('/')}"

        for attempt_index in range(_FUEL_ECONOMY_MAX_ATTEMPTS):
            try:
                response = self._client.get(
                    url,
                    params=params,
                    headers={
                        "Accept": "application/xml",
                    },
                    timeout=FUEL_ECONOMY_TIMEOUT_SECONDS,
                )
            except httpx.RequestError as exc:
                if attempt_index == _FUEL_ECONOMY_MAX_ATTEMPTS - 1:
                    raise FuelEconomyGovTransportError("FuelEconomy.gov request failed") from exc

                self._sleeper(_FUEL_ECONOMY_RETRY_DELAYS_SECONDS[attempt_index])
                continue

            if not response.is_success:
                if (
                    _is_retryable_http_status(response.status_code)
                    and attempt_index < _FUEL_ECONOMY_MAX_ATTEMPTS - 1
                ):
                    self._sleeper(_FUEL_ECONOMY_RETRY_DELAYS_SECONDS[attempt_index])
                    continue

                raise FuelEconomyGovHTTPError(response.status_code)

            try:
                return fromstring(response.content)
            except ParseError as exc:
                raise FuelEconomyGovResponseError(
                    "FuelEconomy.gov response is not valid XML"
                ) from exc

        raise AssertionError("FuelEconomy.gov retry loop exhausted unexpectedly")


def _is_retryable_http_status(status_code: int) -> bool:
    """Return whether an HTTP status represents a transient provider failure."""

    return status_code == 429 or 500 <= status_code <= 599
