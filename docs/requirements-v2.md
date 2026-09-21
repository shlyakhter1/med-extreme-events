# Requirements v2 — Temporality, Power Outage, emPOWER, Cards 7–8

*As of 2026-09-21. Update to `docs/requirements.md` for the next iteration of `med-extreme-events`. Decisions below were settled in design review; do not reopen them during implementation.*

## 0. Decisions record (settled)

| # | Decision |
| --- | --- |
| D1 | Forecast-vs-observed is modeled as a first-class `temporality` field on `Event` (`forecast | imminent | observed`), mapped per provider; `TriggerConditions` gains an optional `temporality` filter; action phase derives from it; observed events supersede forecast-triggered items for the same (card, facility). |
| D2 | Observed outage fires Cards 5/6 at `outage_pct_min: 10` and Card 3 at `outage_pct_min: 25`, with `sustained_polls_min: 2` debounce. The boolean `outage_forecast` stub is **deleted**. |
| D3 | Heat(/cold)+outage compounding is an **engine-level co-occurrence boost** (acuity bump + `compounding_events` annotation), not compound trigger grammar. Grammar goes to the backlog. |
| D4 | emPOWER is a **parallel measured exposure layer** (cached reference data, monthly vintage), never a replacement for condition denominators; plus one new Card 6 sub-panel `electricity_dependent_dme`. |
| D5 | New cards: **Card 7** (extreme cold × cardiovascular/respiratory) and **Card 8** (wildfire smoke × COPD/asthma) — content in `docs/card-library-additions.md`, same evidence discipline as cards 1–6. |
| D6 | Fixtures built this iteration: **Winter Storm Uri 2021** (new headline/golden test), **Hurricane Ian outage upgrade**, **Canadian smoke July 2026**. Replay catalog (`fixtures/events/CATALOG.md`) lists more without building them. |
| D7 | US hazard-source catalog ships as `docs/hazard-catalog.md` + machine-readable `data/hazard_sources.yaml`. |

## 1. Event taxonomy v2 — temporality

**New enum + Event field** (in `src/xevents/models.py`):

```python
class Temporality(StrEnum):
    FORECAST = "forecast"  # event may occur; days of lead time
    IMMINENT = "imminent"  # event expected/beginning; hours of lead time
    OBSERVED = "observed"  # event measured as occurring now
```

`Event` (currently at `models.py` ~line 393, already carrying CAP `urgency`/`certainty`) gains `temporality: Temporality` (required — every provider must map it; no default, so an unmapped provider fails validation loudly).

**Provider mapping table** (implement as data in each provider; raw values preserved in `Event.metrics`):

| Provider | Mapping |
| --- | --- |
| NWS CAP (`providers/nws.py`) | `*Watch` → forecast; `*Warning`, `*Advisory` → imminent; use CAP `certainty=Observed` → observed when present |
| HeatRisk (stubbed) | forecast |
| AirNow (`providers/airnow.py`) | forecast endpoint → forecast; current observations → observed |
| HMS smoke (`providers/hms.py`) | observed (analysis product) |
| OpenFEMA (`providers/openfema.py`) | observed (declaration = event occurred) |
| EAGLE-I (new `providers/eagle_i.py`) | observed |
| PSPS (backlog) | forecast |
| Replay (`providers/replay.py`) | pass-through from fixture records (fixtures must carry temporality) |

**NWS legacy-name normalization** (required for the Uri fixture): per NWS SCN23-44 the cold products were renamed effective Oct 1, 2024. `providers/nws.py` normalizes legacy → current before matching, storing the raw name in `metrics["raw_nws_event"]`: `Wind Chill Warning → Extreme Cold Warning`, `Wind Chill Watch → Extreme Cold Watch`, `Wind Chill Advisory → Cold Weather Advisory`, `Hard Freeze Warning → Freeze Warning`. Cards list **current** names only.

**Phase derivation** (engine): action items generated from a forecast/imminent event surface `phase: pre_event` (plus `any`) actions; from an observed event, `during_event` (plus `any`). The `Phase` enum on actions is unchanged; this adds the event-side selector it lacked.

**Supersede semantics** (store): the upsert natural key stays (event-family, card, facility); when an *observed* event matches a (card, facility) that already holds an item from a *forecast/imminent* event of the same event family (see §2 outage note), the old item transitions to `SUPERSEDED` (existing `store.py` path) and the new item carries `during_event` actions. Never duplicate; never downgrade observed → forecast.

## 2. Trigger conditions v2

In `TriggerConditions` (`models.py`):
- **Remove** `outage_forecast: bool` (and its branch in `engine.py` `~line 80`).
- **Add** `temporality: Temporality | None` — when set, the event's temporality must match.
- **Add** `outage_pct_min: float | None` (0–100) — percent of county customers out (see §3 denominators).
- **Add** `sustained_polls_min: int | None` (≥1) — condition must hold for N consecutive provider polls before firing (engine tracks per (event-source, county) streaks; applies to any metric-threshold condition but is only used by outage cards for now).
- Update the `at_least_one_condition` validator accordingly and regenerate `cards/card.schema.json` via `scripts/export_card_schema.py`.

**Card trigger updates** (YAML only; clinical strings untouched):
- Cards 5 & 6: replace the `power_outage` stub trigger with `{type: power_outage, conditions: {temporality: observed, outage_pct_min: 10, sustained_polls_min: 2}}`.
- Card 3: add the same with `outage_pct_min: 25`.
- Card versions bump minor; `number` unchanged.

**Cross-hazard note:** a hurricane *forecast* item on Card 5/6 superseded by an *observed outage* is a cross-family supersede — allow it explicitly for the pairs (hurricane_flood → power_outage) on cards 3/5/6, encoded as an engine constant `SUPERSEDE_FAMILIES`, not card data.

## 3. EAGLE-I power-outage provider

New `providers/eagle_i.py`, two modes like every provider:
- **Live:** FEMA public ArcGIS FeatureServer `https://gis.fema.gov/arcgis/rest/services/Partner/PowerOutages_EAGLE_I/FeatureServer` — county-FIPS-keyed JSON, updated hourly; poll hourly, no key. Required attribution string (display in UI wherever outage numbers render): *"Electric customer outage data provided by EAGLE-I, Department of Energy."*
- **Replay:** loader for ORNL EAGLE-I historical county CSVs (15-minute cadence, 2014–2025; blanket DOI 10.13139/ORNLNCCS/1975203 for 2014–2022). Fixture builders slice by state/county/date-range.

**Percent-out denominator:** county customer totals from the Moehl et al. modeled customer dataset (published alongside the EAGLE-I Scientific Data descriptor, Brelsford et al. 2024, DOI 10.1038/s41597-024-03095-5) loaded as reference data (`fixtures/reference/eaglei_customers.csv`, build script in `scripts/`). `outage_pct = customers_out / county_customers × 100`.

**Event shape:** one `power_outage` event per (county, poll) crossing any card's minimum threshold, `temporality=observed`, `metrics: {customers_out, county_customers, outage_pct, poll_streak}`.

**Honest-display requirements:** (a) "customers" are meters/accounts, not people — the provenance popover must say so; (b) ~8% of US customers (small rural/municipal utilities) are uncovered — footnote in UI; (c) feed staleness banner like other providers.

## 4. Co-occurrence boost (engine)

Pure-function addition in `engine.py`: after matching, for every active action item whose card's event family is heat (or cold, Card 7) in a county where an observed `power_outage` event (≥ the lowest card threshold, sustained) is also active, (a) raise the item's acuity rank by one profile-defined step (`profiles/va.yaml` gains `co_occurrence_boost` config), and (b) stamp `compounding_events: [<outage event id>]` on the item (new optional ActionItem field, persisted). Symmetric case (outage item during active heat/cold) gets the same annotation. Deterministic, covered by the Uri golden test. No compound trigger grammar.

## 5. emPOWER reference layer

- Build script `scripts/build_empower.py` pulls the public emPOWER REST service (HHS ArcGIS; ZIP + county de-identified monthly counts of electricity-dependent-DME Medicare beneficiaries) into `fixtures/reference/empower.csv`; cached like PLACES/VetPop, refreshed manually (monthly vintage recorded in the file header).
- `denominators.py` gains an `empower_dme` source keyed county/ZIP → catchment rollup.
- **Display rule:** on outage-triggered items, show both lines with provenance: the condition-based veteran estimate (existing) *and* "M electricity-dependent Medicare beneficiaries in catchment (emPOWER, measured; Medicare proxy — not veteran-specific)". emPOWER never silently replaces a veteran denominator (schema `CodeSystem.EMPOWER` already exists for the coding).
- **Ranking rule:** for `power_outage` events, facility ranking uses `outage_pct × empower_dme_count` as the acuity multiplier (measured × measured), with the formula in the provenance popover.
- **Card 6 change:** add sub-panel `electricity_dependent_dme` (home O₂ concentrators, ventilators, CPAP/BiPAP, home-dialysis equipment; `device_classes` with `system: empower`), `denominator_key: empower_dme`. Clinical strings for this sub-panel come from `docs/card-library-additions.md` (reviewed content), not code.

## 6. Cards 7 & 8

Content in `docs/card-library-additions.md`; transcribed to `cards/07-cold-cardio-respiratory.yaml` and `cards/08-smoke-copd-asthma.yaml` under the existing schema discipline (verbatim clinical strings, tiered claims, sources). Card 7 triggers on the post-2024 cold taxonomy (normalized per §1); Card 8 on `aqi_min` and HMS smoke density. Both participate in the co-occurrence boost (cold+outage; smoke card has no boost pairing this iteration).

## 7. Catalogs

- `fixtures/events/CATALOG.md`: replay-scenario catalog (this iteration ships ~9 entries; 3 with built fixtures, the rest feasibility-annotated). Machine-readable index optional this iteration.
- `docs/hazard-catalog.md` + `data/hazard_sources.yaml`: US hazard event/source catalog — event type, source, access, granularity, cadence, temporality mapping, licensing flags, card mapping, integration status (`integrated | this_iteration | backlog`). The YAML is documentation-grade (not loaded by code yet); a future iteration may drive provider registration from it.

## 8. Invariants (unchanged + new)

Unchanged: no PHI; clinical strings only from reviewed card docs; engine pure; provenance on every number; never advise stopping/changing medication; evidence tiers enforced at load.
New: EAGLE-I attribution string wherever outage data renders; customers≠people and coverage-gap footnotes; emPOWER always labeled as measured Medicare proxy; legacy NWS names normalized with raw preserved; every Event must carry temporality.
