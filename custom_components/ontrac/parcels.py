"""Canonical parcel shape, status mapping and list helpers.

Everything in this module is a **pure function** — no I/O, no Home Assistant
objects beyond the config entry's options. That is deliberate: it keeps the
carrier-specific mapping apart from the coordinator, and it makes the mapping
trivially unit-testable without spinning up HA.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    DEFAULT_DELIVERED_FILTER_AMOUNT,
    DEFAULT_DELIVERED_FILTER_TYPE,
    HISTORY_MAX_EVENTS,
    TRACKING_URL,
    ParcelStatus,
)

_LOGGER = logging.getLogger(__name__)

NEW_ISSUE_URL = (
    "https://github.com/ha-parcel-integrations/ha-ontrac/issues/new"
    "?template=unrecognised_status.yml"
)

# OnTrac status vocabulary mapping from EventCode to canonical ParcelStatus.
# Checked against canonical-shape.md with the enum open.
_STATUS_MAP: dict[str, ParcelStatus] = {
    "EXRL": ParcelStatus.REGISTERED,        # data received, parcel not yet in the network
    "INRL": ParcelStatus.REGISTERED,        # data received, parcel not yet in the network
    "ORIG": ParcelStatus.IN_TRANSIT,        # origin scan
    "ARRD": ParcelStatus.IN_TRANSIT,        # arrived at facility
    "SFCT": ParcelStatus.IN_TRANSIT,        # arrived at final servicing facility
    "FCTF": ParcelStatus.IN_TRANSIT,        # departed facility for transfer
    "LOAD": ParcelStatus.IN_TRANSIT,        # loaded onto vehicle
    "OFDL": ParcelStatus.OUT_FOR_DELIVERY,  # out for delivery
    "DLVD": ParcelStatus.DELIVERED,         # delivered
    "BCLD": ParcelStatus.PROBLEM,           # delivery attempted; business closed
    "NDMI": ParcelStatus.PROBLEM,           # incomplete address needs correction
}

# Keys already warned about, so each unconfirmed shape is logged only once
# per HA session instead of on every poll.
_warned: set[str] = set()

# The only Status display buckets seen on the wire. Never mapped to
# ParcelStatus directly (see map_parcel_status's docstring) but a new one is
# still worth a warning: it may signal a status family this integration has
# never observed.
_KNOWN_DISPLAY_STATUSES = frozenset({"Not Yet Received", "In Transit", "Pending", "Delivered"})

# Package-level fields that were null/empty in the only capture this
# integration is built from. A populated one is new evidence, worth a
# warning — but never its value, since these fields carry a real name,
# address or delivery photo.
_SENSITIVE_CONSIGNEE_FIELDS = ("Name", "Contact", "Address1")
_SENSITIVE_PACKAGE_FIELDS = ("SignatureImageString", "SignatureImageFormat", "PodText")

_KNOWN_WEIGHT_UNITS = frozenset({"lbs", "kg"})
_KNOWN_DIMENSION_UNITS = frozenset({"in", "cm"})


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key in _warned:
        return
    _warned.add(key)
    _LOGGER.warning(message, *args)


def _warn_unmapped_status(code: str) -> None:
    """Log an unmapped carrier status once, with a copy-paste issue link."""
    _warn_once(
        f"status:{code}",
        "Unrecognised OnTrac status — help us map it. Open an issue "
        "and paste this line: %s\n  status=%s → reported as 'unknown'",
        NEW_ISSUE_URL,
        code,
    )


def _warn_unknown_display_status(value: str) -> None:
    """Warn once for a ``Status`` bucket outside the four seen on the wire."""
    _warn_once(
        f"display-status:{value}",
        "Unrecognised OnTrac Status value — open an issue and paste this "
        "line: %s\n  Status=%s",
        NEW_ISSUE_URL,
        value,
    )


def _warn_sensitive_field(field: str) -> None:
    """Warn once that a field this integration never exposes was populated — keys only."""
    _warn_once(
        f"sensitive:{field}",
        "OnTrac response populated the %s field, which this integration "
        "does not expose — open an issue (no need to attach the value): %s",
        field,
        NEW_ISSUE_URL,
    )


def _warn_attributes_present(attributes: dict) -> None:
    """Warn once that ``Attributes`` is non-empty — keys only, never values."""
    _warn_once(
        "attributes-present",
        "OnTrac response has a non-empty Attributes object — open an "
        "issue and paste this line: %s\n  keys=%s",
        NEW_ISSUE_URL,
        sorted(attributes),
    )


def _warn_unknown_units(field: str, value: Any) -> None:
    """Warn once for a weight/dimension unit outside the two seen on the wire."""
    _warn_once(
        f"units:{field}:{value!r}",
        "Unrecognised OnTrac %s value — open an issue and paste this "
        "line: %s\n  %s=%r",
        field,
        NEW_ISSUE_URL,
        field,
        value,
    )


def map_parcel_status(code: str | None) -> ParcelStatus:
    """Map an OnTrac EventCode to a canonical :class:`ParcelStatus`.

    ``None`` (a not-yet-scanned parcel) reports ``unknown`` silently; an
    unrecognised code reports ``unknown`` with a one-shot warning.
    """
    if not code:
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    _warn_unmapped_status(code)
    return ParcelStatus.UNKNOWN


def map_event_status(code: str | None) -> ParcelStatus | None:
    """Map a history entry's EventCode to a canonical status, or ``None``.

    Unmapped codes keep ``status: null`` on the history entry (rather than
    ``unknown``, so a consumer can tell "no mapping" from "mapped to unknown")
    and warn once, reusing the parcel-status one-shot set.
    """
    if not code:
        return None
    mapped = _STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    _warn_unmapped_status(code)
    return None


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string to an aware datetime, or ``None`` on failure.

    Naive values are treated as UTC so a list always sorts without crashing on
    a mixed set.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_iso_timestamp(value: Any) -> str | None:
    """Return an ISO 8601 string for an API timestamp field.

    Numbers are treated as **epoch milliseconds** — the common case for the
    consumer APIs in this suite. Strings pass through untouched; their
    consumers are guarded by :func:`parse_iso`. Adjust the numeric branch if
    your carrier stamps in seconds.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value)


def format_dimensions(
    length: float | None, width: float | None, height: float | None
) -> dict[str, Any] | None:
    """Return the canonical ``dimensions`` dict, or ``None`` when incomplete.

    Units contract: **centimetres**, with ``text`` pre-formatted as
    ``"L x W x H cm"`` (integer values, lowercase ``x``) so dashboards can show
    a dimension without doing their own formatting. Convert before calling if
    the carrier reports millimetres or inches.
    """
    if length is None or width is None or height is None:
        return None
    return {
        "length": length,
        "width": width,
        "height": height,
        "text": f"{int(length)} x {int(width)} x {int(height)} cm",
    }


def build_history(
    events: list | None, *, max_events: int = HISTORY_MAX_EVENTS
) -> list[dict]:
    """Build the canonical ``history`` list from the carrier's event list.

    Each entry is ``{timestamp, status, raw_status}`` — identical across all
    suite carriers, and top-level (not under ``raw``) so it survives the
    aggregator's ``strip_raw()``. ``raw_status`` is the carrier's own EventCode.
    Sorted oldest → newest and capped to the most recent ``max_events``.
    """
    parseable: list[tuple[datetime, dict]] = []
    unparseable: list[dict] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        timestamp = to_iso_timestamp(event.get("UtcEventDateTime"))
        if not timestamp:
            continue
        event_code = event.get("EventCode")
        display_status = event.get("Status")
        if display_status and display_status not in _KNOWN_DISPLAY_STATUSES:
            _warn_unknown_display_status(display_status)
        entry = {
            "timestamp": timestamp,
            "status": map_event_status(event_code),
            "raw_status": event_code,
        }
        parsed = parse_iso(timestamp)
        if parsed is None:
            unparseable.append(entry)
        else:
            parseable.append((parsed, entry))
    parseable.sort(key=lambda item: item[0])
    ordered = [entry for _, entry in parseable] + unparseable
    return ordered[-max_events:]


def tracking_url(tracking_code: str | None) -> str | None:
    """Construct the consumer tracking deep-link for a parcel."""
    if not tracking_code:
        return None
    return TRACKING_URL.format(tracking_code=tracking_code)


def normalize_parcel(raw: dict, *, include_history: bool = False) -> dict:
    """Return a carrier-agnostic parcel dict with the payload under ``raw``.

    OnTrac specific field mapping according to the canonical contract.
    """
    tracking_code = raw.get("Tracking")

    # Sort events by UtcEventDateTime to determine the newest event for status
    events = raw.get("Events") or []
    sorted_events: list[tuple[datetime, dict]] = []
    if isinstance(events, list):
        for e in events:
            if isinstance(e, dict):
                dt = parse_iso(e.get("UtcEventDateTime"))
                if dt:
                    sorted_events.append((dt, e))
        sorted_events.sort(key=lambda x: x[0])

    newest_event = sorted_events[-1][1] if sorted_events else {}
    status_code = newest_event.get("EventCode")
    status = map_parcel_status(status_code)
    delivered = status is ParcelStatus.DELIVERED

    newest_display_status = newest_event.get("Status")
    if newest_display_status and newest_display_status not in _KNOWN_DISPLAY_STATUSES:
        _warn_unknown_display_status(newest_display_status)

    # Unit conversions:
    # Weight: WeightUnits "lbs" -> kg (x 0.45359237), "kg" -> kg
    weight = None
    raw_weight = raw.get("Weight")
    weight_units = raw.get("WeightUnits")
    if raw_weight is not None and isinstance(raw_weight, (int, float)):
        if weight_units == "lbs":
            weight = round(float(raw_weight) * 0.45359237, 2)
        elif weight_units == "kg":
            weight = round(float(raw_weight), 2)
        elif weight_units is not None:
            _warn_unknown_units("WeightUnits", weight_units)

    # Dimensions: DimensionUnits "in" -> cm (x 2.54), "cm" -> cm
    dim_units = raw.get("DimensionUnits")
    raw_l = raw.get("Length")
    raw_w = raw.get("Width")
    raw_h = raw.get("Height")
    dimensions = None
    if (
        raw_l is not None
        and isinstance(raw_l, (int, float))
        and raw_w is not None
        and isinstance(raw_w, (int, float))
        and raw_h is not None
        and isinstance(raw_h, (int, float))
    ):
        if dim_units == "in":
            dimensions = format_dimensions(
                float(raw_l) * 2.54, float(raw_w) * 2.54, float(raw_h) * 2.54
            )
        elif dim_units == "cm":
            dimensions = format_dimensions(float(raw_l), float(raw_w), float(raw_h))
        elif dim_units is not None:
            _warn_unknown_units("DimensionUnits", dim_units)

    # Sender / Receiver:
    origin = raw.get("Origin") or {}
    consignee = raw.get("Consignee") or {}

    for field in _SENSITIVE_CONSIGNEE_FIELDS:
        if consignee.get(field):
            _warn_sensitive_field(f"Consignee.{field}")
    for field in _SENSITIVE_PACKAGE_FIELDS:
        if raw.get(field):
            _warn_sensitive_field(field)
    attributes = raw.get("Attributes")
    if isinstance(attributes, dict) and attributes:
        _warn_attributes_present(attributes)

    sender = None
    if origin.get("City") and origin.get("State"):
        sender = f"{origin['City']}, {origin['State']}"
    elif origin.get("City"):
        sender = origin["City"]

    receiver = None
    if consignee.get("City") and consignee.get("State"):
        receiver = f"{consignee['City']}, {consignee['State']}"
    elif consignee.get("City"):
        receiver = consignee["City"]

    # Delivery timestamps:
    delivered_at = (
        to_iso_timestamp(raw.get("UtcDeliveryDateTime")) if delivered else None
    )
    planned_to = (
        None if delivered else to_iso_timestamp(raw.get("UtcExpectedDeliveryDateTime"))
    )

    return {
        "carrier": "OnTrac",
        "barcode": tracking_code,
        "sender": sender,
        "receiver": receiver,
        "status": status,
        "raw_status": status_code,
        "delivered": delivered,
        "delivered_at": delivered_at,
        "planned_from": None,
        "planned_to": planned_to,
        "pickup": False,
        "pickup_point": None,
        "url": tracking_url(tracking_code),
        "weight": weight,
        "dimensions": dimensions,
        "history": build_history(events) if include_history else None,
        "raw": raw,
    }


def sort_parcels_by_ts(
    parcels: list[dict], key_field: str, *, descending: bool = False
) -> list[dict]:
    """Return normalised parcels sorted by the ISO timestamp at ``key_field``.

    The suite's sort contract: incoming/outgoing ascending on ``planned_from``,
    delivered descending on ``delivered_at``. Parcels whose value is missing or
    unparseable always sort to the end, regardless of ``descending``.
    """
    with_ts: list[tuple[datetime, dict]] = []
    without_ts: list[dict] = []
    for parcel in parcels:
        parsed = parse_iso(parcel.get(key_field))
        if parsed is None:
            without_ts.append(parcel)
        else:
            with_ts.append((parsed, parcel))
    with_ts.sort(key=lambda item: item[0], reverse=descending)
    return [parcel for _, parcel in with_ts] + without_ts


def apply_delivered_filter(parcels: list[dict], entry: ConfigEntry) -> list[dict]:
    """Trim the delivered list per the entry's retention option.

    ``parcels`` must already be sorted newest-first. ``days`` keeps deliveries
    from the last N days (an unparseable ``delivered_at`` is kept rather than
    silently dropped); the ``parcels`` type keeps the N most recent. Parcels
    stay *tracked* either way — this only controls what the delivered sensor
    shows.
    """
    options = entry.options
    filter_type = options.get(
        CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE
    )
    amount = int(
        options.get(CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT)
    )
    if filter_type == "days":
        cutoff = datetime.now(timezone.utc) - timedelta(days=amount)
        return [
            parcel
            for parcel in parcels
            if (parsed := parse_iso(parcel.get("delivered_at"))) is None
            or parsed >= cutoff
        ]
    return parcels[:amount]
