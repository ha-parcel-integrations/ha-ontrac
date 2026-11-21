# Working in this repository

Home Assistant custom integration for **OnTrac** parcel tracking.
Distributed via HACS; not part of HA core. One carrier in the
[ha-parcel-integrations](https://github.com/ha-parcel-integrations) suite,
**generated from ha-carrier-template** — everything outside *Carrier-specific
notes* is suite-wide; when in doubt check the template or a sibling repo.
No DTO layer.

## Shared conventions — fetch when relevant

Suite-wide rules live in
[`.github/CONVENTIONS.md`](https://github.com/ha-parcel-integrations/.github/blob/main/CONVENTIONS.md)
and are **not** repeated here. Don't fetch it every session — fetch it **before**
you act in one of these areas:

| Before you … | Fetch `CONVENTIONS.md` § |
|---|---|
| touch entities, sensors, config/options flow, coordinator, diagnostics, translations | *Home Assistant developer docs* (its table points on to the canonical HA page — don't rely on memory) |
| add/rename a parcel field, a `ParcelStatus`, or a bus event; change the sort/first-refresh; touch unmapped-status logging | *Parcel contract* — exact key set, units, sort, events + suppression; `test_parcels.py::test_normalize_publishes_exactly_the_canonical_keys` guards the key set |
| change which optional field this carrier populates vs. always returns `None` | Update `const.py`'s `CAPABILITIES` in the same commit — it feeds the comparison table on the docs site, so a field that starts (or stops) coming back non-null and isn't reflected there is a wrong claim on the website, not just a stale comment. If this carrier has more than one backend (a country-specific transport, not just a config option) with genuinely different field support, `CAPABILITIES` should be a `CAPABILITIES_BY_VARIANT` dict instead — one frozenset per backend, so a field only some backends populate doesn't get silently intersected away or overclaimed for the rest. See ha-dpd's or ha-gls's `const.py` for a live example |
| ship anything while below 1.0.0 (unconfirmed data) | *Pre-1.0 releases* — one-shot WARNINGs for every guessed shape/code |
| consider "fixing" a lint/pattern the skill flags (poll interval, inline client, sync requests) | *Deliberate skill divergences* — likely intentional, don't re-flag |
| commit, bump, tag, release, or write release notes; add a feature without a test | *Workflow / Commits / Versioning / Testing* |

**Structure, options flow, dynamic polling and module layout are suite-wide**
and identical in every carrier — the authoritative spec is
[`ha-carrier-template/scaffold/CLAUDE.md`](https://github.com/ha-parcel-integrations/ha-carrier-template/blob/main/scaffold/CLAUDE.md).
Where this repo diverges from it, that is recorded below under
*Divergences from the scaffold*.

**Suite-wide tripwires, kept inline on purpose:**
- **First refresh in `__init__.py`, before `async_forward_entry_setups`** — from
  a forwarded platform HA can't catch `ConfigEntryNotReady` and half-sets-up the
  entry. Runtime-only; tests don't catch a regression.
- **Setup stale-entity sweep is scoped to `domain == "sensor"` and skips
  `non_parcel_unique_ids`** — else it deletes the refresh button / the
  summary+diagnostic sensors. Add a new non-parcel sensor's unique_id to the set.
- **Per-parcel sensors are removed by the summary sensor** via
  `entity_registry.async_remove` (self-removal races and leaves ghosts).

## Carrier-specific notes

- **Pickup sensors exist, awaiting data.** Both `awaiting_pickup` and
  `en_route_to_pickup_point` are exposed, as the contract requires of a carrier
  that may deliver to pickup points. Pending: none of the twelve confirmed live
  `EventCode`s is a pickup-point arrival, so no code maps to `at_pickup_point`
  yet and both sensors read 0. `pickup` is `is_pickup(None, status,
  event_statuses)` (no structured route flag is known); `pickup_point` stays
  `None` until a real parcel shows a point name. Once a real parcel or a fuller
  code capture shows a pickup-point code, map it to `at_pickup_point`.
- **Keyless, code-based tracking:** Endpoint `https://webtrack.ontrac.com/PackageServices/tracking/{tracking_code}` needs no credentials, API keys, or cookies.
- **Not-found is structured HTTP 404:** Unknown tracking codes return `404` with an RFC9110 ProblemDetails JSON body (`{"Title": "Not Found", "Status": 404}`). This is handled as a pending parcel (`None`), not an error. Any non-JSON 404 or outage raises `OnTracApiError`.
- **Status vocabulary:** Mapped strictly by `EventCode` (not `Status` which is
  too coarse). A 2026-10-17 sweep of fourteen real parcels confirmed twelve of
  the thirteen mapped codes live — every one below except `FCTF` — and produced
  no unmapped code at all. `ExpectedDeliveryDate`, `UtcDeliveryDateTime`,
  `Weight` and the dimension fields were populated on all fourteen. Return and
  pickup-point codes remain unseen:
  - `EXRL`, `INRL` → `registered`
  - `ORIG`, `ARRD`, `SFCT`, `FCTF`, `LOAD` → `in_transit`
  - `OFDL` → `out_for_delivery`
  - `DLVD` → `delivered`
  - `BCLD`, `NDMI`, `UTLV`, `ONHD` → `problem` (`UTLV`: attempt left the package
    over a security or signature requirement; `ONHD`: held until the recipient
    supplies address details or instructions)
  - **`NFRP` is deliberately unmapped.** OnTrac files it under its "Delivered"
    bucket, but its own description says the order was transferred to another
    carrier — not a delivery, and the reply never says what happens next. It
    stays `unknown` with the one-shot WARNING (pinned by a test) until a real
    parcel settles it. Do not map it from the carrier's "Delivered" label.
- **Unit conversions:** `WeightUnits == "lbs"` converted to kg (`× 0.45359237`), `DimensionUnits == "in"` converted to cm (`× 2.54`).
- **ETA & timestamps:** `planned_from`/`planned_to` come from `ExpectedDeliveryDate` (a bare date, so the whole local day, `00:00:00`-`23:59:59`) through `planned_window`; the `UtcExpectedDeliveryDateTime` moment (a `21:00` end-of-day cut-off, not a window start) is only used when the date is missing: its local calendar date, in the moment's own offset (or America/New_York for a `Z` value, whose UTC date can be a day late), becomes a whole-day window, and its offset also dates the bare date. Both are emptied for `delivered`, `at_pickup_point` and `returning`. `UtcDeliveryDateTime` is `delivered_at`, only when delivered.
- **Sender / receiver:** `None`. The payload carries no sender or addressee name, only city/state, and a location is never a name.
- **Privacy & Diagnostics:** `Consignee`, `VpodImageUrl` (doorstep photos), signature fields, and all event-level location fields (`City`/`State`/`PostalCode`) are strictly redacted in `TO_REDACT`.
- **API mechanics:** Full documentation lives in `carrier-research/ontrac/api/`.

## Divergences from the scaffold

Everything not listed here follows the scaffold exactly.

## Running tests

```
python -m pytest tests/ --cov=custom_components.ontrac
```

Coverage must stay **above 95%** (silver `test-coverage` rule). Run before
committing. A code change updates the README + this file + `docs/` in the same
commit; the API reference lives in this carrier's own directory in the private
`carrier-research/<slug>/api/`, never in this repo.
