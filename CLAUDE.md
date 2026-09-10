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

- **No `awaiting_pickup` sensor yet — unconfirmed, not structural.** Of the
  eleven confirmed live `EventCode`s, none is a pickup-point arrival
  (carrier-research's `ontrac.md`); `pickup`/`pickup_point` stay
  `False`/`None` in `parcels.py`. That is "unseen so far," not "cannot
  happen" — revisit once a real parcel or a fuller code capture settles it.
  See `.github/CONVENTIONS.md`'s pickup-point convention.
- **Keyless, code-based tracking:** Endpoint `https://webtrack.ontrac.com/PackageServices/tracking/{tracking_code}` needs no credentials, API keys, or cookies.
- **Not-found is structured HTTP 404:** Unknown tracking codes return `404` with an RFC9110 ProblemDetails JSON body (`{"Title": "Not Found", "Status": 404}`). This is handled as a pending parcel (`None`), not an error. Any non-JSON 404 or outage raises `OnTracApiError`.
- **Status vocabulary:** Mapped strictly by `EventCode` (not `Status` which is too coarse):
  - `EXRL`, `INRL` → `registered`
  - `ORIG`, `ARRD`, `SFCT`, `FCTF`, `LOAD` → `in_transit`
  - `OFDL` → `out_for_delivery`
  - `DLVD` → `delivered`
  - `BCLD`, `NDMI` → `problem`
- **Unit conversions:** `WeightUnits == "lbs"` converted to kg (`× 0.45359237`), `DimensionUnits == "in"` converted to cm (`× 2.54`).
- **ETA & timestamps:** `planned_from` is `None`; `planned_to` is `UtcExpectedDeliveryDateTime` (cleared on delivered parcels). `UtcDeliveryDateTime` is used as `delivered_at`.
- **Sort key:** the suite contract sorts active parcels on `planned_from`, but OnTrac never supplies one, which would leave every active parcel in the unordered no-timestamp bucket. `coordinator.py` therefore sorts on `planned_to`, and `sensor.py`/`calendar.py` fall back to `planned_to` when `planned_from` is `None`. Deliberate deviation — do not "fix" it back to the template.
- **Privacy & Diagnostics:** `Consignee`, `VpodImageUrl` (doorstep photos), signature fields, and all event-level location fields (`City`/`State`/`PostalCode`) are strictly redacted in `TO_REDACT`.
- **API mechanics:** Full documentation lives in `carrier-research/ontrac/api/`.

## Divergences from the scaffold

Everything not listed here follows the scaffold exactly.

*Dynamic polling* — OnTrac never sets `planned_from` (see *Carrier-specific
notes*), so the hot tier collapses to "hot whenever a tracked parcel is
`out_for_delivery`".

## Running tests

```
python -m pytest tests/ --cov=custom_components.ontrac
```

Coverage must stay **above 95%** (silver `test-coverage` rule). Run before
committing. A code change updates the README + this file + `docs/` in the same
commit; the API reference lives in this carrier's own directory in the private
`carrier-research/<slug>/api/`, never in this repo.
