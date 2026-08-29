"""Tests for the pure parcel-mapping helpers.

These need no Home Assistant instance — the whole point of keeping
``parcels.py`` free of I/O is that the carrier-specific mapping (the part you
rewrite per carrier) can be tested as plain functions.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontrac.const import (
    CAPABILITIES,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    DOMAIN,
    KNOWN_CAPABILITIES,
    ParcelStatus,
)
from custom_components.ontrac.parcels import (
    apply_delivered_filter,
    build_history,
    format_dimensions,
    map_event_status,
    map_parcel_status,
    normalize_parcel,
    parse_iso,
    sort_parcels_by_ts,
    to_iso_timestamp,
)

from .payloads import active_sample, delivered_sample, event

# ---------------------------------------------------------------------------
# map_parcel_status / map_event_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("EXRL", ParcelStatus.REGISTERED),
        ("INRL", ParcelStatus.REGISTERED),
        ("ORIG", ParcelStatus.IN_TRANSIT),
        ("ARRD", ParcelStatus.IN_TRANSIT),
        ("SFCT", ParcelStatus.IN_TRANSIT),
        ("FCTF", ParcelStatus.IN_TRANSIT),
        ("LOAD", ParcelStatus.IN_TRANSIT),
        ("OFDL", ParcelStatus.OUT_FOR_DELIVERY),
        ("DLVD", ParcelStatus.DELIVERED),
        ("BCLD", ParcelStatus.PROBLEM),
        ("NDMI", ParcelStatus.PROBLEM),
    ],
)
def test_map_parcel_status_known(code, expected):
    assert map_parcel_status(code) == expected


def test_map_parcel_status_missing_is_unknown():
    assert map_parcel_status(None) == ParcelStatus.UNKNOWN
    assert map_parcel_status("") == ParcelStatus.UNKNOWN


def test_map_parcel_status_unmapped_is_unknown():
    assert map_parcel_status("TELEPORTED") == ParcelStatus.UNKNOWN


def test_map_event_status_missing_and_unmapped_are_none():
    """History keeps ``null`` rather than ``unknown`` so consumers can tell
    "no mapping" from "mapped to unknown"."""
    assert map_event_status(None) is None
    assert map_event_status("SOMETHING_NEW") is None
    assert map_event_status("DLVD") == ParcelStatus.DELIVERED


def test_unmapped_status_warns_only_once(caplog):
    assert map_parcel_status("ABDUCTED") == ParcelStatus.UNKNOWN
    assert map_parcel_status("ABDUCTED") == ParcelStatus.UNKNOWN
    assert caplog.text.count("ABDUCTED") == 1
    assert "issues/new" in caplog.text


# ---------------------------------------------------------------------------
# pre-1.0 one-shot warnings for unconfirmed shapes (BUILD_PLAN.md §5)
# ---------------------------------------------------------------------------


def test_unrecognised_display_status_warns_once(caplog):
    raw = active_sample()
    raw["Events"][0]["Status"] = "Returned"
    normalize_parcel(raw)
    normalize_parcel(raw)
    assert caplog.text.count("Status=Returned") == 1


def test_known_display_status_does_not_warn(caplog):
    normalize_parcel(active_sample())
    assert "Unrecognised OnTrac Status" not in caplog.text


def test_populated_consignee_name_warns_without_value(caplog):
    raw = delivered_sample()
    raw["Consignee"]["Name"] = "Jane Doe"
    normalize_parcel(raw)
    normalize_parcel(raw)
    assert caplog.text.count("Consignee.Name") == 1
    assert "Jane Doe" not in caplog.text


def test_populated_signature_field_warns_without_value(caplog):
    raw = delivered_sample()
    raw["SignatureImageString"] = "base64-blob-not-a-real-signature"
    normalize_parcel(raw)
    assert "SignatureImageString" in caplog.text
    assert "base64-blob-not-a-real-signature" not in caplog.text


def test_null_consignee_and_signature_fields_do_not_warn(caplog):
    normalize_parcel(delivered_sample())
    assert "sensitive" not in caplog.text.lower()


def test_nonempty_attributes_warns_with_keys_only(caplog):
    raw = delivered_sample()
    raw["Attributes"] = {"FragileHandling": True}
    normalize_parcel(raw)
    normalize_parcel(raw)
    assert caplog.text.count("Attributes") >= 1
    assert "FragileHandling" in caplog.text
    assert "True" not in caplog.text


def test_empty_attributes_does_not_warn(caplog):
    normalize_parcel(delivered_sample())
    assert "non-empty Attributes" not in caplog.text


def test_unrecognised_weight_units_warns_once(caplog):
    raw = delivered_sample()
    raw["WeightUnits"] = "oz"
    normalize_parcel(raw)
    normalize_parcel(raw)
    assert caplog.text.count("WeightUnits=") == 1


def test_unrecognised_dimension_units_warns_once(caplog):
    raw = delivered_sample()
    raw["DimensionUnits"] = "mm"
    normalize_parcel(raw)
    normalize_parcel(raw)
    assert caplog.text.count("DimensionUnits=") == 1


def test_known_units_do_not_warn(caplog):
    normalize_parcel(delivered_sample())
    assert "Unrecognised OnTrac" not in caplog.text


# ---------------------------------------------------------------------------
# timestamp helpers
# ---------------------------------------------------------------------------


def test_parse_iso_handles_z_naive_and_garbage():
    assert parse_iso("2026-04-29T13:12:42Z").tzinfo is not None
    # A naive value is assumed UTC so mixed lists still sort.
    assert parse_iso("2026-04-29T13:12:42").tzinfo == timezone.utc
    assert parse_iso("not-a-date") is None
    assert parse_iso(None) is None


def test_to_iso_timestamp_converts_epoch_milliseconds():
    assert to_iso_timestamp(1784203767167) == "2026-07-16T12:09:27.167000+00:00"
    assert to_iso_timestamp("2026-04-29T13:12:42Z") == "2026-04-29T13:12:42Z"
    assert to_iso_timestamp(None) is None
    assert to_iso_timestamp(10**20) is None  # out of range -> None, never raises


def test_format_dimensions_needs_all_three_axes():
    assert format_dimensions(30, 20, 10) == {
        "length": 30,
        "width": 20,
        "height": 10,
        "text": "30 x 20 x 10 cm",
    }
    assert format_dimensions(30, None, 10) is None


# ---------------------------------------------------------------------------
# build_history
# ---------------------------------------------------------------------------


def test_build_history_orders_oldest_to_newest():
    history = build_history(delivered_sample()["Events"])
    assert len(history) == 7
    assert history[0]["raw_status"] == "EXRL"
    assert history[0]["status"] == ParcelStatus.REGISTERED
    assert history[-1]["status"] == ParcelStatus.DELIVERED


def test_build_history_caps_to_max_events():
    events = [
        event("ORIG", f"2026-04-{day:02d}T10:00:00+00:00")
        for day in range(1, 26)
    ]
    assert len(build_history(events, max_events=20)) == 20


def test_build_history_handles_missing_and_malformed():
    assert build_history(None) == []
    assert build_history([{"EventCode": "ORIG"}]) == []  # no timestamp
    assert build_history(["not-a-dict"]) == []


def test_build_history_keeps_unparseable_timestamp_last():
    history = build_history(
        [
            event("EXRL", "2026-04-24T10:00:00+00:00"),
            event("ORIG", "not-a-date"),
        ]
    )
    assert [entry["raw_status"] for entry in history] == ["EXRL", "ORIG"]


# ---------------------------------------------------------------------------
# normalize_parcel — the canonical contract
# ---------------------------------------------------------------------------

CANONICAL_KEYS = [
    "carrier",
    "barcode",
    "sender",
    "receiver",
    "status",
    "raw_status",
    "delivered",
    "delivered_at",
    "planned_from",
    "planned_to",
    "pickup",
    "pickup_point",
    "url",
    "weight",
    "dimensions",
    "history",
    "raw",
]


def test_normalize_publishes_exactly_the_canonical_keys():
    """The aggregator and cross-carrier dashboards depend on this key set."""
    assert list(normalize_parcel(delivered_sample())) == CANONICAL_KEYS


def test_capabilities_are_known_values():
    """A typo here would silently misreport this carrier on the docs site."""
    assert CAPABILITIES <= KNOWN_CAPABILITIES


def test_capabilities_match_what_normalize_parcel_actually_returns():
    """Every declared CAPABILITIES entry must come true somewhere in a sample."""
    delivered = normalize_parcel(delivered_sample())
    active = normalize_parcel(active_sample())
    with_history = normalize_parcel(delivered_sample(), include_history=True)

    if "weight" in CAPABILITIES:
        assert delivered["weight"] is not None
    if "dimensions" in CAPABILITIES:
        assert delivered["dimensions"] is not None
    if "delivery_window" in CAPABILITIES:
        assert active["planned_from"] is not None or active["planned_to"] is not None
    if "pickup_point" in CAPABILITIES:
        assert delivered["pickup_point"] is not None
    if "url" in CAPABILITIES:
        assert delivered["url"] is not None
    if "history" in CAPABILITIES:
        assert with_history["history"] is not None


def test_normalize_delivered_parcel():
    parcel = normalize_parcel(delivered_sample())
    assert parcel["carrier"] == "OnTrac"
    assert parcel["barcode"] == "1LSCY9R00DELIV"
    assert parcel["sender"] == "MOONACHIE, NJ"
    assert parcel["receiver"] == "ORLANDO, FL"
    assert parcel["status"] == ParcelStatus.DELIVERED
    assert parcel["raw_status"] == "DLVD"
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-03-19T13:08:26-04:00"
    # A delivered parcel drops its ETA — the window is meaningless once it has
    # arrived.
    assert parcel["planned_from"] is None
    assert parcel["planned_to"] is None
    assert parcel["url"] == "https://www.ontrac.com/tracking/?number=1LSCY9R00DELIV"
    assert parcel["weight"] == 2.27
    assert parcel["dimensions"]["text"] == "40 x 30 x 15 cm"
    assert parcel["history"] is None  # opt-in, default off


def test_normalize_history_is_opt_in():
    parcel = normalize_parcel(delivered_sample(), include_history=True)
    assert len(parcel["history"]) == 7
    assert parcel["history"][0]["status"] == ParcelStatus.REGISTERED


def test_normalize_active_parcel_has_window():
    parcel = normalize_parcel(active_sample())
    assert parcel["status"] == ParcelStatus.OUT_FOR_DELIVERY
    assert parcel["delivered"] is False
    assert parcel["planned_from"] is None
    assert parcel["planned_to"] == "2026-03-19T21:00:00-04:00"


def test_normalize_pending_placeholder():
    """A tracked-but-not-yet-scanned code still yields a full parcel dict."""
    parcel = normalize_parcel({"Tracking": "1LSCY9R00000000"})
    assert parcel["status"] == ParcelStatus.UNKNOWN
    assert parcel["delivered"] is False
    assert parcel["raw_status"] is None
    assert parcel["weight"] is None
    assert parcel["dimensions"] is None
    assert parcel["history"] is None


def test_normalize_blank_fields_become_none():
    raw = active_sample()
    raw["Origin"] = {}
    raw["Consignee"] = {}
    parcel = normalize_parcel(raw)
    assert parcel["sender"] is None
    assert parcel["receiver"] is None


def test_normalize_metric_units_passthrough():
    raw = active_sample()
    raw["WeightUnits"] = "kg"
    raw["Weight"] = 3.5
    raw["DimensionUnits"] = "cm"
    raw["Length"] = 25
    raw["Width"] = 15
    raw["Height"] = 10
    parcel = normalize_parcel(raw)
    assert parcel["weight"] == 3.5
    assert parcel["dimensions"]["text"] == "25 x 15 x 10 cm"


def test_normalize_keeps_raw_payload():
    raw = active_sample()
    assert normalize_parcel(raw)["raw"] is raw


# ---------------------------------------------------------------------------
# sort_parcels_by_ts
# ---------------------------------------------------------------------------


def test_sort_parcels_ascending_puts_unparseable_last():
    parcels = [
        {"barcode": "a", "planned_from": "2026-05-02T10:00:00Z"},
        {"barcode": "b", "planned_from": None},
        {"barcode": "c", "planned_from": "2026-05-01T10:00:00Z"},
    ]
    ordered = [p["barcode"] for p in sort_parcels_by_ts(parcels, "planned_from")]
    assert ordered == ["c", "a", "b"]


def test_sort_parcels_descending_still_puts_unparseable_last():
    parcels = [
        {"barcode": "a", "delivered_at": "2026-05-02T10:00:00Z"},
        {"barcode": "b", "delivered_at": "nonsense"},
        {"barcode": "c", "delivered_at": "2026-05-01T10:00:00Z"},
    ]
    ordered = [
        p["barcode"]
        for p in sort_parcels_by_ts(parcels, "delivered_at", descending=True)
    ]
    assert ordered == ["a", "c", "b"]


# ---------------------------------------------------------------------------
# apply_delivered_filter
# ---------------------------------------------------------------------------


def _entry(filter_type: str, amount: int) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_DELIVERED_FILTER_TYPE: filter_type,
            CONF_DELIVERED_FILTER_AMOUNT: amount,
        },
        unique_id=DOMAIN,
    )


def _delivered_pair() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {"barcode": "RECENT", "delivered_at": (now - timedelta(days=1)).isoformat()},
        {"barcode": "OLD", "delivered_at": (now - timedelta(days=30)).isoformat()},
    ]


def test_delivered_filter_by_days():
    kept = apply_delivered_filter(_delivered_pair(), _entry("days", 7))
    assert [p["barcode"] for p in kept] == ["RECENT"]


def test_delivered_filter_by_count():
    parcels = _delivered_pair()
    assert apply_delivered_filter(parcels, _entry("parcels", 1)) == parcels[:1]


def test_delivered_filter_keeps_unparseable_timestamp():
    """Better to show a parcel with a broken date than to silently drop it."""
    parcels = [{"barcode": "WEIRD", "delivered_at": "nonsense"}]
    assert apply_delivered_filter(parcels, _entry("days", 7)) == parcels
