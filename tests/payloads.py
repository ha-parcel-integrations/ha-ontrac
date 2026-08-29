"""Sample OnTrac API payloads shared by the test modules."""
from __future__ import annotations

ACTIVE_CODE = "1LSCY9R00ACTIVE"
DELIVERED_CODE = "1LSCY9R00DELIV"


def event(
    event_code: str,
    utc_datetime: str,
    status: str = "In Transit",
    short_desc: str = "In Transit",
    long_desc: str = "In Transit",
    city: str | None = "MOONACHIE",
    state: str | None = "NJ",
    postal_code: str | None = "07074",
    country: str | None = "US",
) -> dict:
    """One entry of OnTrac's Events timeline."""
    return {
        "UtcEventDateTime": utc_datetime,
        "EventCode": event_code,
        "Status": status,
        "EventShortDescription": short_desc,
        "EventLongDescription": long_desc,
        "City": city,
        "State": state,
        "PostalCode": postal_code,
        "Country": country,
    }


def delivered_sample(code: str = DELIVERED_CODE) -> dict:
    """A representative tracking response for a delivered parcel (redacted capture)."""
    return {
        "Tracking": code,
        "Length": 16,
        "Width": 12,
        "Height": 6,
        "DimensionUnits": "in",
        "Weight": 5,
        "WeightUnits": "lbs",
        "ServiceCode": "RD",
        "ServiceDescription": "",
        "Origin": {
            "City": "MOONACHIE",
            "State": "NJ",
            "PostalCode": "07074",
            "Country": "US",
        },
        "Consignee": {
            "Name": None,
            "Contact": None,
            "Phone": None,
            "PhoneExt": None,
            "Address1": None,
            "Address2": None,
            "Address3": None,
            "City": "ORLANDO",
            "State": "FL",
            "PostalCode": "32801",
            "Country": "US",
        },
        "TenderedDate": "2026-03-17",
        "ExpectedDeliveryDate": "2026-03-19",
        "UtcExpectedDeliveryDateTime": "2026-03-19T21:00:00-04:00",
        "UtcDeliveryDateTime": "2026-03-19T13:08:26-04:00",
        "UtcOrderPlaced": "2026-03-16T16:58:13-04:00",
        "Reference1": "REDACTED",
        "Reference2": None,
        "Reference3": None,
        "VpodImageUrl": "https://t.lasership.com/Photo/sample.jpg",
        "SignatureImageString": None,
        "SignatureImageFormat": None,
        "PodText": None,
        "Events": [
            event(
                "DLVD",
                "2026-03-19T17:08:26+00:00",
                status="Delivered",
                short_desc="Package Delivered",
                long_desc="Your package has been delivered",
                city="ORLANDO",
                state="FL",
                postal_code="32801",
            ),
            event(
                "OFDL",
                "2026-03-19T12:45:00+00:00",
                short_desc="Out for Delivery",
                long_desc="Your package is out for delivery",
                city="ORLANDO",
                state="FL",
                postal_code="32801",
            ),
            event(
                "LOAD",
                "2026-03-19T10:15:00+00:00",
                short_desc="Loaded onto vehicle",
                long_desc="Loaded onto vehicle",
                city="ORLANDO",
                state="FL",
                postal_code="32801",
            ),
            event(
                "SFCT",
                "2026-03-19T06:00:00+00:00",
                short_desc="Arrived at Final Servicing Facility",
                long_desc="Arrived at Final Servicing Facility",
                city="ORLANDO",
                state="FL",
                postal_code="32801",
            ),
            event(
                "ARRD",
                "2026-03-18T20:00:00+00:00",
                short_desc="Arrived at Facility",
                long_desc="Arrived at Facility",
                city="ORLANDO",
                state="FL",
                postal_code="32801",
            ),
            event(
                "ORIG",
                "2026-03-17T22:00:00+00:00",
                short_desc="Origin Scan",
                long_desc="Origin Scan",
                city="MOONACHIE",
                state="NJ",
                postal_code="07074",
            ),
            event(
                "EXRL",
                "2026-03-16T17:00:00+00:00",
                status="Not Yet Received",
                short_desc="On its way to OnTrac",
                long_desc="Data received",
                city=None,
                state=None,
                postal_code=None,
                country=None,
            ),
        ],
        "Attributes": {},
    }


def active_sample(code: str = ACTIVE_CODE) -> dict:
    """An out-for-delivery parcel."""
    sample = delivered_sample(code)
    sample["UtcDeliveryDateTime"] = None
    sample["Events"] = sample["Events"][1:]  # Drop DLVD, so OFDL is newest
    return sample


def not_found_body() -> dict:
    """The structured 404 response payload from RFC9110 ProblemDetails."""
    return {
        "Type": "https://tools.ietf.org/html/rfc9110#section-15.5.5",
        "Title": "Not Found",
        "Status": 404,
        "traceId": "00-0123456789abcdef-0123456789abcdef-00",
    }
