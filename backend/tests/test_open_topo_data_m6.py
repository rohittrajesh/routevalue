"""M6-D bounded Open Topo Data adapter tests, with no live HTTP requests."""

import json
from decimal import Decimal
from math import isfinite
from typing import cast

import httpx
import pytest

from routevalue.application.models import RoutePoint
from routevalue.application.terrain import ElevationSample
from routevalue.application.terrain_ports import (
    ElevationProvider,
    ElevationProviderQuotaError,
    ElevationProviderRejectedError,
    ElevationProviderResponseError,
    ElevationProviderUnavailableError,
)
from routevalue.application.terrain_sampling import TerrainSampleLocation
from routevalue.infrastructure.elevation.open_topo_data import (
    OPEN_TOPO_DATA_DEFAULT_DATASET,
    OPEN_TOPO_DATA_MAX_LOCATIONS,
    OpenTopoDataElevationProvider,
)


def _locations(
    count: int = 2,
) -> tuple[TerrainSampleLocation, ...]:
    return tuple(
        TerrainSampleLocation(
            point=RoutePoint(
                latitude=32.88 + index * 0.0001,
                longitude=-117.23,
            ),
            distance_meters=index * 250,
        )
        for index in range(count)
    )


def _response(
    locations: tuple[TerrainSampleLocation, ...],
    elevations: tuple[object, ...] | None = None,
    *,
    dataset: str = "ned10m",
) -> dict[str, object]:
    if elevations is None:
        elevations = tuple(100 + index for index in range(len(locations)))

    return {
        "status": "OK",
        "results": [
            {
                "location": {
                    "lat": place.point.latitude,
                    "lng": place.point.longitude,
                },
                "dataset": dataset,
                "elevation": value,
            }
            for place, value in zip(
                locations,
                elevations,
                strict=True,
            )
        ],
    }


def test_successful_post_normalizes_order_and_original_offsets() -> None:
    places = _locations(3)
    requests: list[httpx.Request] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(request)

        return httpx.Response(
            200,
            json=_response(
                places,
                (112.5, -6, None),
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider: ElevationProvider = OpenTopoDataElevationProvider(client=client)

        samples = provider.get_elevations(places)

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://api.opentopodata.org/v1/ned10m"
    assert requests[0].headers["content-type"] == "application/json"

    payload = json.loads(requests[0].content)

    assert payload == {
        "locations": ("32.8800000,-117.2300000|32.8801000,-117.2300000|32.8802000,-117.2300000"),
        "interpolation": "bilinear",
        "nodata_value": "null",
    }

    assert samples == (
        ElevationSample(
            point=places[0].point,
            distance_meters=0,
            elevation_meters=Decimal("112.5"),
        ),
        ElevationSample(
            point=places[1].point,
            distance_meters=250,
            elevation_meters=Decimal(-6),
        ),
        ElevationSample(
            point=places[2].point,
            distance_meters=500,
            elevation_meters=None,
        ),
    )

    assert all(sample.resolution_meters is None for sample in samples)


def test_empty_batch_returns_without_network() -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("empty input cannot call external services")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(client=client)

        assert provider.get_elevations(()) == ()


def test_exactly_100_points_allowed_in_one_request() -> None:
    places = _locations(100)
    calls = 0

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls

        calls += 1

        return httpx.Response(
            200,
            json=_response(places),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(client=client)

        result = provider.get_elevations(places)

    assert OPEN_TOPO_DATA_MAX_LOCATIONS == 100
    assert len(result) == 100
    assert calls == 1


def test_101_points_rejected_before_network() -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("over-budget input cannot make a network request")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(client=client)

        with pytest.raises(
            ValueError,
            match="exceeds 100",
        ):
            provider.get_elevations(_locations(101))


def test_unsupported_dataset_rejected_without_http_request() -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client,
        pytest.raises(
            ValueError,
            match="unsupported",
        ),
    ):
        OpenTopoDataElevationProvider(
            client=client,
            dataset="../../bad",
        )


def test_alternative_allowlisted_dataset_is_requested() -> None:
    places = _locations(2)

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == "/v1/mapzen"

        return httpx.Response(
            200,
            json=_response(
                places,
                dataset="mapzen",
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(
            client=client,
            dataset="mapzen",
        )

        assert len(provider.get_elevations(places)) == 2


def test_constant_defaults_are_explicit() -> None:
    assert OPEN_TOPO_DATA_DEFAULT_DATASET == "ned10m"


@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (429, ElevationProviderQuotaError),
        (500, ElevationProviderUnavailableError),
        (503, ElevationProviderUnavailableError),
        (400, ElevationProviderRejectedError),
        (403, ElevationProviderRejectedError),
    ],
)
def test_http_failures_are_structured(
    status_code: int,
    exception: type[Exception],
) -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(status_code)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(client=client)

        with pytest.raises(exception):
            provider.get_elevations(_locations())


def test_transport_error_is_structured() -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "no route to host",
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(
            ElevationProviderUnavailableError,
            match="request failed",
        ),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(_locations())


@pytest.mark.parametrize(
    ("payload", "exception"),
    [
        (
            {"status": "SERVER_ERROR"},
            ElevationProviderUnavailableError,
        ),
        (
            {"status": "INVALID_REQUEST"},
            ElevationProviderRejectedError,
        ),
        (
            {"status": "BAD"},
            ElevationProviderResponseError,
        ),
        (
            [],
            ElevationProviderResponseError,
        ),
        (
            {"status": "OK"},
            ElevationProviderResponseError,
        ),
        (
            {
                "status": "OK",
                "results": [],
            },
            ElevationProviderResponseError,
        ),
        (
            {
                "status": "OK",
                "results": [{}],
            },
            ElevationProviderResponseError,
        ),
    ],
)
def test_status_and_shape_failures(
    payload: object,
    exception: type[Exception],
) -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(exception),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(_locations())


def test_non_json_response_is_rejected() -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            text="bad json",
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(
            ElevationProviderResponseError,
            match="invalid JSON",
        ),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(_locations())


@pytest.mark.parametrize(
    "value",
    [
        True,
        "100",
        float("nan"),
        float("inf"),
    ],
)
def test_invalid_elevations_rejected(
    value: object,
) -> None:
    payload = _response(
        _locations(),
        (value, 123),
    )

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        if isinstance(value, float) and not isfinite(value):
            return httpx.Response(
                200,
                text=json.dumps(payload),
            )

        return httpx.Response(
            200,
            json=payload,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(
            ElevationProviderResponseError,
            match="elevation",
        ),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(_locations())


def test_mismatched_provider_dataset_rejected() -> None:
    payload = _response(
        _locations(),
        dataset="mapzen",
    )

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(
            ElevationProviderResponseError,
            match="dataset",
        ),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(_locations())


def test_null_elevation_may_omit_dataset_without_fabricating_value() -> None:
    places = _locations()

    payload = _response(
        places,
        (None, 10),
    )

    results = cast(
        list[dict[str, object]],
        payload["results"],
    )

    del results[0]["dataset"]

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = OpenTopoDataElevationProvider(client=client).get_elevations(places)

    assert result[0].elevation_meters is None


def test_result_coordinate_swap_detected() -> None:
    places = _locations()

    payload = _response(places)

    results = cast(
        list[dict[str, object]],
        payload["results"],
    )

    results.reverse()

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(
            ElevationProviderResponseError,
            match="coordinates",
        ),
    ):
        OpenTopoDataElevationProvider(client=client).get_elevations(places)


def test_small_coordinate_roundtrip_is_accepted() -> None:
    places = (
        TerrainSampleLocation(
            point=RoutePoint(
                latitude=32.881234567,
                longitude=-117.231234567,
            ),
            distance_meters=0,
        ),
    )

    payload = _response(
        places,
        (12,),
    )

    results = cast(
        list[dict[str, object]],
        payload["results"],
    )

    results[0]["location"] = {
        "lat": 32.8812346,
        "lng": -117.2312346,
    }

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        sample = OpenTopoDataElevationProvider(client=client).get_elevations(places)[0]

    assert sample.elevation_meters == Decimal(12)


def test_invalid_input_type_or_order_rejected_before_network() -> None:
    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError("invalid batch cannot call external services")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = OpenTopoDataElevationProvider(client=client)

        with pytest.raises(
            TypeError,
            match="locations",
        ):
            provider.get_elevations((None,))  # type: ignore[arg-type]

        with pytest.raises(
            ValueError,
            match="strictly increase",
        ):
            provider.get_elevations(tuple(reversed(_locations())))
