"""Tests for the OnTrac API client."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.ontrac.api import (
    OnTracApiClient,
    OnTracApiError,
)
from tests.payloads import not_found_body

CODE = "1LSCY9R00000000"


def _session_returning(
    status: int, body: object = None, headers: dict | None = None
) -> MagicMock:
    response = AsyncMock()
    response.status = status
    response.headers = headers or {}
    if isinstance(body, str):
        response.json = AsyncMock(side_effect=json.JSONDecodeError("x", body, 0))
    else:
        response.json = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


async def test_get_parcel_returns_parcel_on_success():
    session = _session_returning(
        200, {"Packages": [{"Tracking": CODE}]}
    )
    client = OnTracApiClient(session)

    parcel = await client.async_get_parcel(CODE)

    assert parcel["Tracking"] == CODE
    assert CODE in session.get.call_args[0][0]


async def test_get_parcel_returns_none_when_not_found():
    """An unknown code returns structured 404 ProblemDetails, treated as None."""
    client = OnTracApiClient(
        _session_returning(404, not_found_body())
    )
    assert await client.async_get_parcel("1LSCY9R00000000") is None


async def test_get_parcel_returns_none_on_empty_packages():
    """An empty Packages list returns None."""
    client = OnTracApiClient(
        _session_returning(200, {"Packages": []})
    )
    assert await client.async_get_parcel(CODE) is None


async def test_get_parcel_warns_once_on_multiple_packages(caplog):
    """More than one Packages element is unexpected — use the first, warn once."""
    client = OnTracApiClient(
        _session_returning(
            200, {"Packages": [{"Tracking": CODE}, {"Tracking": "1LSOTHER0000000"}]}
        )
    )
    parcel = await client.async_get_parcel(CODE)
    parcel2 = await client.async_get_parcel(CODE)

    assert parcel["Tracking"] == CODE
    assert parcel2["Tracking"] == CODE
    assert caplog.text.count("Packages elements") == 1


async def test_get_parcel_raises_on_500_status():
    client = OnTracApiClient(_session_returning(500, {}))
    with pytest.raises(OnTracApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_404_with_non_json_or_unexpected_body():
    client = OnTracApiClient(_session_returning(404, "<html>blocked</html>"))
    with pytest.raises(OnTracApiError):
        await client.async_get_parcel(CODE)

    client_bad_json = OnTracApiClient(_session_returning(404, {"error": "unexpected"}))
    with pytest.raises(OnTracApiError):
        await client_bad_json.async_get_parcel(CODE)


async def test_get_parcel_raises_on_unparseable_body():
    client = OnTracApiClient(_session_returning(200, "not json"))
    with pytest.raises(OnTracApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_non_object_body():
    client = OnTracApiClient(_session_returning(200, ["not", "a", "dict"]))
    with pytest.raises(OnTracApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_non_object_package_element():
    client = OnTracApiClient(_session_returning(200, {"Packages": ["not_a_dict"]}))
    with pytest.raises(OnTracApiError):
        await client.async_get_parcel(CODE)


async def test_get_parcel_raises_on_429_with_retry_after():
    client = OnTracApiClient(_session_returning(429, headers={"Retry-After": "30"}))
    with pytest.raises(OnTracApiError) as excinfo:
        await client.async_get_parcel(CODE)
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 30


async def test_get_parcel_429_without_parseable_retry_after():
    """An HTTP-date Retry-After (not seconds) falls back to None."""
    client = OnTracApiClient(
        _session_returning(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    )
    with pytest.raises(OnTracApiError) as excinfo:
        await client.async_get_parcel(CODE)
    assert excinfo.value.retry_after is None


async def test_get_parcel_propagates_network_error():
    """ClientError is left alone — DataUpdateCoordinator already wraps it."""
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    client = OnTracApiClient(session)
    with pytest.raises(aiohttp.ClientError):
        await client.async_get_parcel(CODE)
