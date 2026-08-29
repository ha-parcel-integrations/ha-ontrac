"""Diagnostics support for the OnTrac parcel tracker integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OnTracConfigEntry

# Diagnostics are pasted into public issues, so redact anything that
# identifies a person, an address or a specific parcel. Over-redacting is
# cheap; under-redacting leaks a user's home address into a GitHub thread.
#
# OnTrac specific redaction list from tracking.md:
# Tracking, Consignee block, Reference1-3, VpodImageUrl, SignatureImageString,
# PodText, and every event City/State/PostalCode.
TO_REDACT = {
    # canonical fields we publish ourselves
    "tracking_code",
    "barcode",
    "sender",
    "receiver",
    "url",
    # OnTrac payload fields
    "Tracking",
    "Consignee",
    "Reference1",
    "Reference2",
    "Reference3",
    "VpodImageUrl",
    "SignatureImageString",
    "SignatureImageFormat",
    "PodText",
    "City",
    "State",
    "PostalCode",
    "Address1",
    "Address2",
    "Address3",
    "Contact",
    "Phone",
    "PhoneExt",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OnTracConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the OnTrac config entry."""
    coordinator = entry.runtime_data.coordinator

    return {
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "counts": {
            "incoming_active": len(coordinator.data or []),
            "delivered": len(coordinator.delivered or []),
        },
        "polling": {
            "tier_minutes": coordinator.current_tier_minutes,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "suspended": coordinator.update_interval is None,
        },
        "incoming": async_redact_data(coordinator.data or [], TO_REDACT),
        "delivered": async_redact_data(coordinator.delivered or [], TO_REDACT),
    }
