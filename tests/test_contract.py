"""The parcel contract's checks, run over every normalised sample."""

from datetime import datetime

import pytest

from custom_components.ontrac.const import ParcelStatus
from custom_components.ontrac.parcels import normalize_parcel, parse_iso

from .payloads import active_sample, delivered_sample

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


def _problem() -> dict:
    sample = active_sample()
    sample["Events"][0]["EventCode"] = "BCLD"
    return sample


def _moment_only() -> dict:
    sample = active_sample()
    sample["ExpectedDeliveryDate"] = None
    sample["UtcExpectedDeliveryDateTime"] = "2099-03-19T21:00:00-04:00"
    return sample


def _utc_moment_only() -> dict:
    sample = _moment_only()
    sample["UtcExpectedDeliveryDateTime"] = "2099-03-20T01:00:00Z"
    return sample


def _date_only() -> dict:
    sample = active_sample()
    sample["UtcExpectedDeliveryDateTime"] = None
    return sample


SAMPLES = {
    "delivered": delivered_sample,
    "active": active_sample,
    "problem": _problem,
    "moment_only": _moment_only,
    "utc_moment_only": _utc_moment_only,
    "date_only": _date_only,
    "bare": lambda: {"Tracking": "1LSCY9R00000000"},
}


@pytest.fixture(params=SAMPLES)
def parcel(request) -> dict:
    return normalize_parcel(SAMPLES[request.param]())


def test_keys_and_order(parcel):
    assert list(parcel) == CANONICAL_KEYS


def test_delivered_follows_status(parcel):
    assert parcel["delivered"] is (parcel["status"] is ParcelStatus.DELIVERED)


def test_delivered_at_only_when_delivered(parcel):
    if not parcel["delivered"]:
        assert parcel["delivered_at"] is None


def test_planned_window_is_ordered_and_anchored(parcel):
    if parcel["planned_to"] is not None:
        assert parcel["planned_from"] is not None
        assert parse_iso(parcel["planned_to"]) > parse_iso(parcel["planned_from"])


def test_planned_is_empty_when_the_parcel_is_done_or_waiting(parcel):
    if parcel["status"] in (
        ParcelStatus.DELIVERED,
        ParcelStatus.AT_PICKUP_POINT,
        ParcelStatus.RETURNING,
    ):
        assert parcel["planned_from"] is None
        assert parcel["planned_to"] is None


def test_pickup_is_a_bool_and_the_point_needs_it(parcel):
    assert isinstance(parcel["pickup"], bool)
    if not parcel["pickup"]:
        assert parcel["pickup_point"] is None


def test_an_active_parcel_has_a_window():
    parcel = normalize_parcel(active_sample())
    assert parcel["planned_from"] == "2026-03-19T00:00:00-04:00"
    assert parcel["planned_to"] == "2026-03-19T23:59:59-04:00"


def test_a_delivered_parcel_is_emptied_and_dated():
    parcel = normalize_parcel(delivered_sample())
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-03-19T13:08:26-04:00"
    assert parcel["planned_from"] is None


def test_a_moment_without_a_date_is_its_whole_local_day():
    parcel = normalize_parcel(_moment_only())
    assert parcel["planned_from"] == "2099-03-19T00:00:00-04:00"
    assert parcel["planned_to"] == "2099-03-19T23:59:59-04:00"


def test_a_utc_moment_is_dated_in_the_carrier_zone():
    # 01:00Z on the 20th is 21:00 on the 19th in New York.
    parcel = normalize_parcel(_utc_moment_only())
    assert parcel["planned_from"] == "2099-03-19T00:00:00-04:00"
    assert parcel["planned_to"] == "2099-03-19T23:59:59-04:00"


def test_a_date_takes_the_offset_of_the_moment():
    sample = active_sample()
    sample["ExpectedDeliveryDate"] = "2026-03-19"
    sample["UtcExpectedDeliveryDateTime"] = "2026-03-19T21:00:00-04:00"
    parcel = normalize_parcel(sample)
    assert parcel["planned_from"] == "2026-03-19T00:00:00-04:00"
    assert parcel["planned_to"] == "2026-03-19T23:59:59-04:00"


def test_a_date_covers_the_whole_day():
    parcel = normalize_parcel(_date_only())
    start = datetime.fromisoformat(parcel["planned_from"])
    end = datetime.fromisoformat(parcel["planned_to"])
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end.hour, end.minute, end.second, end.microsecond) == (23, 59, 59, 0)
    assert start.date() == end.date()
