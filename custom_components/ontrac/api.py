"""OnTrac public tracking API client.

OnTrac (LaserShip/OnTrac group) uses a keyless, code-based model where each
tracking number is registered by the user. The endpoint responds with a JSON
envelope containing a `Packages` array for known parcels, and returns HTTP 404
with a structured RFC9110 ProblemDetails JSON payload for unknown tracking
codes.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import TRACKING_API_URL

_LOGGER = logging.getLogger(__name__)

NEW_ISSUE_URL = (
    "https://github.com/ha-parcel-integrations/ha-ontrac/issues/new"
    "?template=unrecognised_status.yml"
)

# One-shot: every observed response has had exactly one element in Packages.
_warned_multi_package = False


class OnTracApiError(Exception):
    """Raised when an OnTrac API call returns an unexpected response."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the status code and the ``Retry-After`` header, if any."""
        super().__init__(f"OnTrac API request failed: {detail}")
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class OnTracApiClient:
    """Client for the public OnTrac tracking endpoint.

    No authentication: the endpoint is keyed on the tracking code alone.
    Returns the parcel dict for a known parcel (from Packages[0]), or None
    when the endpoint returns HTTP 404 with a structured ProblemDetails body.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with an aiohttp session."""
        self._session = session

    def _warn_multi_package(self, count: int) -> None:
        """Warn once that a response carried more than one Packages element."""
        global _warned_multi_package
        if _warned_multi_package:
            return
        _warned_multi_package = True
        _LOGGER.warning(
            "OnTrac response had %d Packages elements instead of the usual "
            "one; only the first is used — open an issue and paste this "
            "line: %s",
            count,
            NEW_ISSUE_URL,
        )

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one parcel's tracking details.

        Returns the parcel dict for a known parcel, or ``None`` when the
        endpoint reports the code as unknown (structured 404 ProblemDetails).
        Any other non-200 status or unexpected body raises :class:`OnTracApiError`;
        network errors propagate as ``aiohttp.ClientError``.
        """
        url = TRACKING_API_URL.format(tracking_code=tracking_code)
        headers = {
            "User-Agent": "HomeAssistant-OnTrac/0.9.1",
            "Accept": "application/json",
        }
        async with self._session.get(url, headers=headers) as response:
            if response.status == 429:
                retry_after_header = response.headers.get("Retry-After")
                try:
                    retry_after = float(retry_after_header) if retry_after_header else None
                except ValueError:
                    retry_after = None  # an HTTP-date, not seconds; let the caller's own backoff handle it
                raise OnTracApiError(
                    "HTTP 429", status_code=429, retry_after=retry_after
                )

            if response.status == 200:
                try:
                    payload = await response.json(content_type=None)
                except ValueError as err:
                    raise OnTracApiError(f"unparseable body ({err})") from err

                if not isinstance(payload, dict):
                    raise OnTracApiError("unexpected body (not a JSON object)")

                packages = payload.get("Packages")
                if not isinstance(packages, list) or not packages:
                    return None
                if len(packages) > 1:
                    self._warn_multi_package(len(packages))

                package = packages[0]
                if not isinstance(package, dict):
                    raise OnTracApiError("unexpected package element (not a JSON object)")
                return package

            if response.status == 404:
                # Check for semantic 404 ProblemDetails JSON
                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    raise OnTracApiError("HTTP 404 (non-JSON body)")

                if isinstance(payload, dict) and (
                    payload.get("Title") == "Not Found" or payload.get("Status") == 404
                ):
                    return None
                raise OnTracApiError("HTTP 404 (unexpected JSON error body)")

            raise OnTracApiError(f"HTTP {response.status}")
