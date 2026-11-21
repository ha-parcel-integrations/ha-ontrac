"""Tests for OnTrac sensor property logic."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.ontrac.const import ParcelStatus
from custom_components.ontrac.sensor import (
    OnTracAwaitingPickupSensor,
    OnTracDeliveredParcelsSensor,
    OnTracEnRouteToPickupPointSensor,
    OnTracIncomingParcelsSensor,
    OnTracLastUpdateSensor,
    OnTracNextDeliverySensor,
    OnTracParcelSensor,
)


def _entry(entry_id: str = "e1") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


def _coordinator(data: list[dict], delivered: list[dict] | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.delivered = delivered if delivered is not None else []
    return coordinator


def _parcel(
    barcode: str,
    status: ParcelStatus = ParcelStatus.IN_TRANSIT,
    pickup: bool = False,
    planned_from: str | None = None,
    planned_to: str | None = None,
) -> dict:
    return {
        "carrier": "OnTrac",
        "barcode": barcode,
        "sender": "Sender",
        "receiver": None,
        "status": status,
        "pickup": pickup,
        "planned_from": planned_from,
        "planned_to": planned_to,
    }


def test_incoming_counts_and_lists():
    coordinator = _coordinator([_parcel("A"), _parcel("B")])
    sensor = OnTracIncomingParcelsSensor(coordinator, _entry(), lambda _: None, set())
    assert sensor.native_value == 2
    assert len(sensor.extra_state_attributes["parcels"]) == 2


def test_parcel_sensor_status_and_attributes():
    parcel = _parcel("A", status=ParcelStatus.OUT_FOR_DELIVERY)
    sensor = OnTracParcelSensor(_coordinator([parcel]), _entry(), "A")
    assert sensor.native_value == ParcelStatus.OUT_FOR_DELIVERY
    assert sensor.extra_state_attributes["barcode"] == "A"


def test_parcel_sensor_missing_barcode():
    sensor = OnTracParcelSensor(_coordinator([_parcel("A")]), _entry(), "OTHER")
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_next_delivery_picks_earliest():
    coordinator = _coordinator(
        [
            _parcel("A", planned_from="2099-05-02T10:00:00Z"),
            _parcel("B", planned_from="2099-05-01T10:00:00Z"),
        ]
    )
    sensor = OnTracNextDeliverySensor(coordinator, _entry())
    assert sensor.native_value == datetime(2099, 5, 1, 10, 0, tzinfo=UTC)
    assert sensor.extra_state_attributes["barcode"] == "B"


def test_next_delivery_skips_a_window_that_has_ended():
    coordinator = _coordinator(
        [
            _parcel(
                "OLD",
                planned_from="2000-01-01T00:00:00Z",
                planned_to="2000-01-01T23:59:59Z",
            ),
            _parcel("STALE", planned_from="2000-01-02T10:00:00Z"),
            _parcel("NEW", planned_from="2099-01-01T10:00:00Z"),
        ]
    )
    sensor = OnTracNextDeliverySensor(coordinator, _entry())
    assert sensor.extra_state_attributes["barcode"] == "NEW"


def test_next_delivery_ignores_planned_to_without_planned_from():
    sensor = OnTracNextDeliverySensor(
        _coordinator([_parcel("A", planned_to="2099-01-01T10:00:00Z")]), _entry()
    )
    assert sensor.native_value is None


def test_next_delivery_prefers_planned_from_over_planned_to():
    coordinator = _coordinator(
        [
            _parcel(
                "A",
                planned_from="2099-05-01T10:00:00Z",
                planned_to="2099-05-09T10:00:00Z",
            ),
        ]
    )
    sensor = OnTracNextDeliverySensor(coordinator, _entry())
    assert sensor.native_value == datetime(2099, 5, 1, 10, 0, tzinfo=UTC)


def test_next_delivery_none_without_moments():
    sensor = OnTracNextDeliverySensor(_coordinator([_parcel("A")]), _entry())
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_next_delivery_skips_unparseable_moment():
    coordinator = _coordinator(
        [
            _parcel("A", planned_from="not-a-date"),
            _parcel("B", planned_from="2099-05-01T10:00:00Z"),
        ]
    )
    sensor = OnTracNextDeliverySensor(coordinator, _entry())
    assert sensor.extra_state_attributes["barcode"] == "B"


def test_delivered_sensor():
    coordinator = _coordinator(
        [], delivered=[_parcel("D", status=ParcelStatus.DELIVERED)]
    )
    sensor = OnTracDeliveredParcelsSensor(coordinator, _entry())
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["parcels"][0]["barcode"] == "D"


def test_last_update_sensor():
    coordinator = _coordinator([])
    moment = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    coordinator.last_success_time = moment
    sensor = OnTracLastUpdateSensor(coordinator, _entry())
    assert sensor.native_value == moment


def test_en_route_counts_only_active_pickup_parcels_not_at_the_point():
    sensor = OnTracEnRouteToPickupPointSensor(
        _coordinator(
            [
                _parcel("A", pickup=True),
                _parcel("B", ParcelStatus.AT_PICKUP_POINT, pickup=True),
                _parcel("C", ParcelStatus.RETURNING, pickup=True),
                _parcel("D", pickup=False),
            ]
        ),
        _entry(),
    )
    assert sensor.native_value == 1
    assert [p["barcode"] for p in sensor.extra_state_attributes["parcels"]] == ["A"]
    assert sensor.unique_id == "e1_en_route_to_pickup_point"


def test_awaiting_pickup_counts_only_parcels_at_the_point():
    sensor = OnTracAwaitingPickupSensor(
        _coordinator(
            [
                _parcel("A", pickup=True),
                _parcel("B", ParcelStatus.AT_PICKUP_POINT, pickup=True),
                _parcel("C", ParcelStatus.RETURNING, pickup=True),
            ]
        ),
        _entry(),
    )
    assert sensor.native_value == 1
    assert sensor.unique_id == "e1_awaiting_pickup"


def test_pickup_sensors_empty_without_data():
    coordinator = _coordinator([])
    coordinator.data = None
    assert OnTracAwaitingPickupSensor(coordinator, _entry()).native_value == 0
    assert OnTracEnRouteToPickupPointSensor(coordinator, _entry()).native_value == 0
