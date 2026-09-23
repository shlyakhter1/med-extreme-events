# Implementation Plan v2 — M6–M10

*As of 2026-09-21. Continues M0–M5 (`docs/implementation-plan.md`). Implements `docs/requirements-v2.md`. One milestone per Claude Code session, in order; each ends with its *Done when* verified, `make lint test` green, and a `PROGRESS.md` entry.*

## Success criteria for the iteration

1. Replaying **Winter Storm Uri (Feb 2021, TX)** fires Card 7 (cold) from normalized legacy CAP products, fires Cards 3/5/6 from EAGLE-I observed-outage thresholds, and applies the cold×outage co-occurrence boost — all asserted by a golden-file test.
2. The upgraded **Hurricane Ian** replay shows the forecast→observed supersede: hurricane-watch items on Cards 5/6 transition to SUPERSEDED when EAGLE-I FL outage events land, with during-event actions surfacing.
3. Replaying **Canadian smoke July 2026** fires Card 8 for Midwest/Northeast facilities from AirNow AQI + HMS density.
4. `EVENT_MODE=live` polls the FEMA EAGLE-I FeatureServer hourly with zero code change; outage numbers render with the DOE attribution string and customers≠people footnote.
5. Outage-triggered items display both denominators (veteran estimate + emPOWER measured proxy) with formulas in the provenance popover.
6. `make demo` still rebuilds everything from empty in one command.

## M6 — Temporality axis + trigger schema v2

Touch: `src/xevents/models.py`, `src/xevents/engine.py`, all `src/xevents/providers/*.py`, `scripts/export_card_schema.py` output, `cards/03|05|06-*.yaml`, `fixtures/events/*/build.py` (records gain temporality), existing golden tests.

1. Add `Temporality` enum; add required `Event.temporality`; per-provider mapping tables per requirements §1, raw values into `metrics`.
2. `TriggerConditions`: remove `outage_forecast`; add `temporality`, `outage_pct_min`, `sustained_polls_min`; update validator; regenerate `cards/card.schema.json`.
3. Engine: phase derivation (forecast/imminent → pre_event+any; observed → during_event+any); streak tracking for `sustained_polls_min`; `SUPERSEDE_FAMILIES = {(hurricane_flood → power_outage): [cards 3,5,6]}` cross-family supersede constant wired into the existing store supersede path.
4. NWS legacy cold-name normalization table (SCN23-44) with `raw_nws_event` preserved.
5. Update cards 3/5/6 triggers per requirements §2 (minor version bumps).

*Done when:* schema regenerated and all 6 cards validate; a unit test proves an unmapped provider temporality fails loudly; phase-derivation and streak unit tests pass; existing golden tests updated and green.

## M7 — EAGLE-I provider (live + replay) + customer denominators

Touch: new `src/xevents/providers/eagle_i.py`, `scripts/build_eaglei_customers.py`, `fixtures/reference/`, `profiles/va.yaml` (thresholds config), `src/xevents/web/` (attribution + footnotes).

1. Live mode: FEMA FeatureServer client (county FIPS, hourly poll, cache raw pulls to fixtures like other providers; no key; honest staleness banner).
2. Replay mode: ORNL historical county CSV loader (15-min cadence), sliced by state/date.
3. Moehl county-customer reference table + `outage_pct` computation; one observed `power_outage` Event per (county, poll) crossing the lowest configured threshold, metrics per requirements §3.
4. UI: DOE attribution string on every outage render; customers≠people + ~8% coverage footnotes in the provenance popover.

*Done when:* live smoke test (network-marked) parses the FeatureServer; a synthetic replay slice produces expected events incl. debounce behavior (2-poll streak) in unit tests.

## M8 — emPOWER reference layer + Card 6 sub-panel

Touch: `scripts/build_empower.py`, `fixtures/reference/empower.csv`, `src/xevents/denominators.py`, `cards/06-outage-dialysis.yaml`, web templates.

1. Build script pulls the public emPOWER REST service (ZIP + county), records vintage month in the header; cached reference data, manual refresh.
2. `empower_dme` denominator source with county/ZIP → catchment rollup.
3. Dual-denominator display + ranking rule (`outage_pct × empower_dme_count`) with formula provenance; Medicare-proxy label mandatory.
4. Card 6: add `electricity_dependent_dme` sub-panel (device_classes `system: empower`), clinical strings transcribed verbatim from `docs/card-library.md` §Card 6 sub-panel (formerly card-library-additions.md).

*Done when:* an outage item for a fixture county shows both numbers with correct provenance text; ranking test proves emPOWER multiplier ordering; Card 6 revalidates.

## M9 — Cards 7 & 8 + cold taxonomy + co-occurrence boost

Touch: `cards/07-cold-cardio-respiratory.yaml`, `cards/08-smoke-copd-asthma.yaml`, `src/xevents/engine.py` (boost), `profiles/va.yaml` (acuity classes for cold/smoke; `co_occurrence_boost` config), denominator keys (PLACES CHD/COPD/asthma already loaded in M3 — add any missing profile keys).

1. Transcribe Cards 7 and 8 from `docs/card-library.md` (formerly card-library-additions.md) — clinical strings verbatim; tiered claims with sources; schema-valid.
2. Boost per requirements §4: acuity bump + `compounding_events` annotation (new optional ActionItem field, persisted through `store.py`), symmetric annotation, deterministic.
3. Extend the NWS provider's accepted event set with the cold/winter products (normalized names).

*Done when:* Cards 7/8 load; boost unit tests (heat+outage, cold+outage, no-boost when outage below threshold) pass; a malformed untier-ed claim in a test card is rejected.

## M10 — Fixtures, catalogs, dashboard polish

Touch: `fixtures/events/uri_2021/`, `ian_2022/` (upgrade), `smoke_canada_2026/`, `fixtures/events/CATALOG.md`, `docs/hazard-catalog.md`, `data/hazard_sources.yaml`, web templates, golden tests.

1. **Uri 2021 fixture:** IEM CAP archive slice (TX, Feb 10–20, 2021 — legacy Wind Chill products exercise normalization) + ORNL EAGLE-I 2021 TX counties. Builder + README with retrieval provenance, like existing fixtures.
2. **Ian upgrade:** add EAGLE-I 2022 FL slice to the existing fixture; extend its golden file for the supersede path.
3. **Canadian smoke July 2026 fixture:** HMS polygons + AirNow archive (Jul 14–20, 2026, Upper Midwest/Great Lakes → Northeast) + concurrent NWS heat alerts (central-US heat dome) for narrative; adapt `smoke_nyc_2023/build.py`.
4. New golden tests: Uri (headline — asserts success criterion 1 exactly), Ian supersede, smoke 2026.
5. Ship `fixtures/events/CATALOG.md` and `docs/hazard-catalog.md` + `data/hazard_sources.yaml` (drop-in files provided in this bundle — copy, then keep current).
6. Dashboard: temporality badge on events (forecast/imminent/observed), outage layer on the map (county fill by `outage_pct`), `compounding_events` chip on boosted items, scenario switcher entries for the three new/updated fixtures.

*Done when:* all six success criteria pass through the browser; `make demo` green from empty; recorded run-through updated.

## CLAUDE.md delta (append to repo CLAUDE.md)

- Every `Event` must carry `temporality`; provider mapping tables are data, raw source values preserved in `metrics`.
- EAGLE-I attribution string is mandatory wherever outage data renders: "Electric customer outage data provided by EAGLE-I, Department of Energy." Customers are meters, not people — say so in provenance.
- emPOWER numbers are always labeled as measured Medicare proxy; they never replace veteran denominators.
- Cards 7/8 clinical strings come only from `docs/card-library.md` (formerly card-library-additions.md); legacy NWS cold-product names are normalized in the provider, never listed in cards.
- No compound trigger grammar — compounding is the engine boost only (backlog item for grammar).

## Risks

- FEMA FeatureServer is a partner service without a formal SLA — cache raw pulls, tolerate schema drift with a contract smoke test.
- ORNL yearly datasets have differing column conventions across years — normalize in the loader, assert with fixture tests.
- emPOWER REST layer naming/fields can shift on portal updates — pin the queried layer id in the build script and fail loudly.
- July 2026 AirNow archive access runs through the post-migration consolidated endpoints — verify historical query support early in M10; fall back to EPA AQS daily data if the archive route is limited.
- IEM CAP archive for Feb 2021 uses legacy product names by design — that is the test, not a bug.
