# OnTrac Parcel Tracker

[![Release](https://img.shields.io/github/v/release/ha-parcel-integrations/ha-ontrac.svg)](https://github.com/ha-parcel-integrations/ha-ontrac/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 💬 Questions or feedback? Join the discussion on the [Home Assistant community](https://community.home-assistant.io/t/packages-postnl-dhl-nl-dpd-and-gls-parcel-integration/112433/).

A custom Home Assistant integration that tracks your [OnTrac](https://www.ontrac.com) parcels. No account is needed — you enter the tracking code yourself, just like on the OnTrac website.

Part of the [ha-parcel-integrations](https://github.com/ha-parcel-integrations) family: it publishes the same canonical parcel format, statuses and events as the other carrier integrations, so it plugs straight into the [Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator) and cross-carrier automations.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Options](#options)
- [Removal](#removal)
- [Sensors](#sensors)
- [Parcel status reference](#parcel-status-reference)
- [Events](#events)
- [Services](#services)
- [Examples](#examples)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Related integrations](#related-integrations)
- [Disclaimer](#disclaimer)
- [Contributing](#contributing)
- [License](#license)

## Features

- Track any number of OnTrac parcels by tracking code — no account needed
- Per-parcel sensor with the canonical status (`registered` / `in_transit` / `out_for_delivery` / `delivered` / …), the carrier's own status text, the expected delivery window and a tracking deep-link
- Summary sensors: incoming parcels, next delivery, recently delivered parcels
- Read-only **Deliveries** calendar with the expected delivery windows
- `ontrac.track_parcel` / `ontrac.untrack_parcel` services, so a dashboard button can add a parcel
- Events + device triggers for no-code automations (parcel registered, status changed, delivered, delivery time changed)
- Opt-in per-parcel status history
- Manual refresh button and a diagnostic last-update sensor

## Requirements

- Home Assistant 2024.12 or newer
- An OnTrac parcel and its tracking code (from the shipping
  confirmation email or the missed-delivery card) — no account needed

## Installation

### HACS (recommended)

1. In HACS, choose the three-dot menu → **Custom repositories**.
2. Add `https://github.com/ha-parcel-integrations/ha-ontrac` as an **Integration**.
3. Install **OnTrac** and restart Home Assistant.

### Manual

Copy `custom_components/ontrac` into your `config/custom_components/` folder and restart Home Assistant.

## Configuration

Add the integration via **Settings → Devices & Services → Add Integration → OnTrac**. There is nothing to fill in: the hub is created immediately (OnTrac tracking needs no account).

Then add parcels via the integration's **Configure** dialog, the [`ontrac.track_parcel`](#services) service, or a [dashboard button](examples/dashboards/add_parcel_card.yaml). The tracking code is on your shipping confirmation email or the missed-delivery card.

## Options

Open **Configure** on the integration entry, then choose **Parcels** or
**Settings**:

| Menu | Section | Option | Default | Description |
|---|---|---|---|---|
| Parcels | — | Add / remove | — | Manage the tracked tracking codes. Changes apply immediately, no restart. |
| Settings | Delivered parcels | Filter by / amount | last 7 days | How long delivered parcels stay visible on the delivered sensor. |
| Settings | Parcel history | Include status history | off | Adds a `history` attribute per parcel with each status update. |

Polling isn't one of these settings: the integration polls on a dynamic,
status-driven schedule (quiet overnight window, faster when a parcel is out
for delivery, stopped entirely once nothing is left to track) with nothing to
configure. See [CLAUDE.md](CLAUDE.md) for the details.

## Removal

Standard HA removal applies: **Settings → Devices & Services → OnTrac → ⋮ → Delete**. Nothing is stored on OnTrac's side.

## Sensors

| Entity | Description |
|---|---|
| `sensor.ontrac_incoming_parcels` | Number of active tracked parcels, full list under the `parcels` attribute |
| `sensor.ontrac_parcel_<code>` | One per tracked parcel; state is the canonical status, attributes carry the full normalised parcel |
| `sensor.ontrac_next_delivery` | Earliest expected delivery moment across all active parcels |
| `sensor.ontrac_delivered_parcels` | Recently delivered parcels (see the retention option) |
| `sensor.ontrac_last_successful_update` | Diagnostic: when OnTrac was last polled successfully |

A delivered parcel moves from its per-parcel sensor to the delivered sensor automatically.

## Parcel status reference

The `status` field is the carrier-agnostic enum shared by the whole integration family:

| Status | Meaning |
|---|---|
| `registered` | Data received, not yet in network (`EXRL`, `INRL`) |
| `in_transit` | In transit / facility transfer (`ORIG`, `ARRD`, `SFCT`, `FCTF`, `LOAD`) |
| `out_for_delivery` | Out for delivery with courier (`OFDL`) |
| `delivered` | Delivered (`DLVD`) |
| `problem` | Delivery blocked by a closed business or incomplete address (`BCLD`, `NDMI`) |
| `unknown` | Not yet scanned / unmapped event code |

The carrier's own human-readable text is always available as `raw_status`.

## Events

The integration fires these on the event bus (also available as device triggers on the OnTrac device):

| Event | When |
|---|---|
| `ontrac_parcel_registered` | A new parcel appears in the active list |
| `ontrac_parcel_status_changed` | A parcel's canonical status changes (`old_status` / `new_status` in the payload), except the final hop to delivered |
| `ontrac_parcel_delivered` | A parcel is delivered |
| `ontrac_parcel_delivery_time_changed` | The expected delivery window changes |

Every payload is the full normalised parcel plus the hub's `device_id`. Events are suppressed on the first refresh after start-up.

## Services

| Service | Fields | Description |
|---|---|---|
| `ontrac.track_parcel` | `tracking_code` | Start tracking a parcel |
| `ontrac.untrack_parcel` | `tracking_code` | Stop tracking a parcel |

## Examples

Ready-to-paste automations and dashboard snippets live in [`examples/`](examples/), including tracking a new parcel straight from a dashboard.

### Community Lovelace cards

Third-party cards that work with this integration's sensors:

- [jonisnet/hki-parcels-card](https://github.com/jonisnet/hki-parcels-card)
- [klaptafel/ha-package-tracker-card](https://github.com/klaptafel/ha-package-tracker-card)

## Debugging

```yaml
logger:
  logs:
    custom_components.ontrac: debug
```

## Troubleshooting

- **A parcel shows `unknown`** — OnTrac has not scanned it yet (their API answers `not_found` until the first scan), or the code is wrong. It will pick up automatically once scanned.
- **A status logs "Unrecognised OnTrac status"** — please [open an issue](https://github.com/ha-parcel-integrations/ha-ontrac/issues/new) with the logged line so the mapping can be extended.

## Related integrations

This integration is part of [**ha-parcel-integrations**](https://github.com/ha-parcel-integrations) — a family of
parcel-carrier integrations that all publish the same canonical parcel format,
statuses and events.

- [**Parcel Aggregator**](https://github.com/ha-parcel-integrations/ha-parcel-aggregator) rolls every installed carrier
  up into one set of sensors.
- Browse [the organisation](https://github.com/ha-parcel-integrations) for the current list of supported carriers.

## Disclaimer

This integration uses the same public tracking endpoint as the OnTrac consumer website. It is not affiliated with, endorsed by, or supported by OnTrac.

## Contributing

Pull requests and issues are welcome. Please open an issue before
submitting a large change.

## License

[MIT](LICENSE)
