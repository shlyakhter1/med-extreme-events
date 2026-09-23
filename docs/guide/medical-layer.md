# Medical layer: facilities, panels, cards and action items

*Part of the [design and user guide](README.md). As of 2026-09-23.*

The medical layer answers: **given the events active now, which VA facilities have
patients at risk, roughly how many, and what should the care team and the patients do?**
It reads `Event` records from the event layer ([events-and-playback.md](events-and-playback.md))
and nothing else from it. It runs in **Mode A**: no patient records, real or synthetic.
Every patient count is an aggregate estimate that carries its formula and sources.

## 1. Pipeline

```
facilities.geojson ──► attribution (county, VISN) ──► catchments (county → station)
                                                              │
VetPop × PLACES × profile rates ──► PanelEstimator ◄──────────┘
                                          │
events ─► engine.match(events, cards, stations, profile, panels) ─► action_items ─► pages / API
                 ▲
     cards/*.yaml + profiles/va.yaml
```

| Stage | Command | Code |
| --- | --- | --- |
| Facility spine, county attribution, catchments | `make load` | `scripts/load_reference.py`, `geography/attribution.py`, `geography/catchment.py` |
| Match events to cards and write action items | `make match` | `scripts/match.py`, `engine.py`, `store.py` |
| Serve | `make serve` | `api.py`, `web/views.py` |

## 2. Facilities and catchments

**Facilities.** The 1,400 VA health facilities from the VA Lighthouse Facilities API are
cached in `fixtures/reference/facilities.geojson`. Each facility is attributed to a county
by point-in-polygon on its coordinates, with the ZIP crosswalk as fallback. `county_source`
records which method was used. VISN comes from the facility record. VA market is not
available (see [data-sources.md](data-sources.md)). One facility is unresolved: Manila VA
Clinic, in the Philippines, has no US county.

**Stations own panels, clinics do not.** Every US county is assigned to its nearest
*anchor station*, a VA Medical Center or Health Care Center (`catchment.anchor_classifications`
in the profile), by great-circle distance to the county's representative point. The result
is 183 stations, each with a catchment of counties. Clinics (CBOCs and others) are linked to
their station by health care system, or to the nearest station otherwise. They display their
station's panel.

**Action items are issued only at stations.** If every clinic in a catchment were issued
items too, the same estimated patients would be counted once per clinic. The first demo had
this bug, which inflated panels several-fold. `scripts/match.py` passes only panel-owning
stations to the engine.

## 3. Panel estimates

`PanelEstimator` (`src/xevents/denominators.py`) turns a station's catchment into an
`Estimate`, which holds a value, a formula, inputs, sources, caveats and component
estimates. The UI renders all of it under "how was this number computed?".

```
veterans_in_catchment = Σ VetPop(county, projection_year) over the catchment
condition_panel       = one of:
    VA-literature rate:  veterans × share_of_veterans[vha_users] × rate      (bipolar, schizophrenia, HF, diabetes)
    national count:      count × veterans_in_catchment / national_veterans   (dialysis)
    PLACES rate:         Σ veterans(county) × PLACES prevalence(county)       (CHD, COPD, asthma: Cards 7 and 8)
card_panel            = condition_panel × class share (profile panel_multipliers), else condition_panel as an upper bound
sub-panels            = condition_panel × sub-panel share, else upper bound   (Card 3: clozapine has a share; LAI and methadone do not)
                        or their own condition panel                          (Card 7: HF, COPD, asthma; Card 8: COPD)
exposure (Card 6)     = Σ emPOWER electricity-dependent DME beneficiaries(county) over the catchment
```

PLACES rates are general-population adult prevalence, applied to veterans; the UI says so.
**The emPOWER exposure is measured, not estimated**: HHS emPOWER counts Medicare
beneficiaries with electricity-dependent equipment claims. It is a proxy population, is
always labeled "measured Medicare proxy", and is shown *beside* the veteran panel, never in
place of it (see [data-sources.md](data-sources.md)).

All rates, shares and scopes come from `profiles/va.yaml`. On load, the estimator checks
national sanity anchors (veterans ±5 %, VHA heart-failure patients ±20 %).

**A card fires only where it implies at least one patient**
(`profile.min_panel_patients = 1.0`). The engine logs the skip together with the computed
panel.

## 4. Playbook cards

The eight cards in `cards/*.yaml` are the clinical content. Each is transcribed verbatim
from `docs/card-library.md` (Cards 1–6) or `docs/card-library-additions.md` (Cards 7, 8 and
the Card 6 electricity-dependent DME sub-panel), the reviewed sources of truth.

| # | Card id | Fires on | Panel basis | Lead window | Acuity (1 = highest) |
| --- | --- | --- | --- | --- | --- |
| 1 | `heat-lithium` | NWS Heat Advisory, Excessive/Extreme Heat Watch or Warning; HeatRisk ≥ orange | bipolar (VHA rate) | 3–7 d | 4 |
| 2 | `heat-antipsychotics` | same heat products | schizophrenia (VHA rate) | 3–7 d | 5 |
| 3 | `hurricane-delivery-interruption` | Hurricane, Tropical Storm or Storm Surge Watch/Warning; Flood Watch/Warning; Flash Flood Warning; **observed outage ≥ 25 % of customers for 2+ polls** | schizophrenia, with clozapine, LAI and methadone sub-panels | 3–7 d | 2 |
| 4 | `heat-heart-failure` | same heat products | heart failure × ACE/ARB/ARNI share | 3–7 d | 6 |
| 5 | `outage-insulin` | Hurricane or Tropical Storm Watch/Warning; **observed outage ≥ 10 % for 2+ polls** | diabetes (VHA rate) | 3–7 d | 3 |
| 6 | `outage-dialysis` | same as Card 5 | dialysis (national count by veteran share), plus the measured emPOWER electricity-dependent DME sub-panel | 3–7 d | 1 (highest) |
| 7 | `cold-cardio-respiratory` | Extreme Cold Watch/Warning, Cold Weather Advisory, Winter Storm Watch/Warning, Ice Storm Warning, Blizzard Warning | coronary heart disease (PLACES), with heart-failure, COPD and asthma sub-panels | 1–3 d | 7 (6 when boosted) |
| 8 | `smoke-copd-asthma` | AirNow AQI ≥ 101; HMS smoke density Medium or Heavy, observed | asthma (PLACES), with a COPD sub-panel | 1–3 d | 8 |

"Observed outage" is an EAGLE-I county reading: percent of customers out, sustained over
consecutive polls (the debounce). Card 7 lists only the current NWS cold-product names; the
NWS provider renames the retired Wind Chill Watch/Warning to them
(`LEGACY_NWS_EVENT_NAMES`), so old archives still fire it.

Acuity is the order in `profile.acuity_order`: dialysis, clozapine/LAI/methadone, insulin,
lithium, antipsychotic heat, heart failure, cold cardio-respiratory, smoke COPD/asthma. The
API's `acuity_rank` is the same order counted from 0, so dialysis is 0 there. A co-occurring
observed outage can raise a heat or cold item one class (§5).

**Where to read the cards.**

- **In the app:** the **Cards** tab (`/card-library`) lists all eight with their triggers,
  population, evidence tier and where each fires in the replays and live; `/card-library/{id}`
  shows one card in full, rendered verbatim from its YAML. This is the most readable view.
- **Clinical source of truth:** [`docs/card-library.md`](../card-library.md) (Cards 1–6,
  cross-cutting caveats and evidence tiers) and
  [`docs/card-library-additions.md`](../card-library-additions.md) (Cards 7, 8 and the Card 6
  DME sub-panel). These are the reviewed texts the YAML is transcribed from.
- **Machine-readable:** `cards/*.yaml`, served as JSON by `GET /cards`.
- **For front-end work:** [`docs/card-reference-for-frontend.md`](../card-reference-for-frontend.md)
  (response shapes and rendering rules).
- **The literature:** [`docs/medical-references.md`](../medical-references.md) lists every
  source the cards cite, card by card, plus background references.

**Anatomy of a card.** A card has `event_triggers` (any one fires the card; all conditions
within a trigger must hold) and a `population_selector` (condition, medication-class and
device codes, the `denominator_key` and sub-panels). It has `actions` per role, where care
team actions are tagged `pre_event` or `during_event`. It also has `escalation` signs (a
null response means the profile's default "Contact your care team."), an `evidence_tier`
with per-claim tiers and source ids, `sources`, `window_days` (3–7), `safety`, and
`care_system_hooks` that point into the profile.

**What the loader rejects** (`src/xevents/cards.py`, enforced by tests): unknown fields, a
claim with no tier, a `weak` tier (the enum has no such value), unknown source ids, duplicate
ids or numbers, a medication card without `safety.do_not_stop_medication: true`, and
malformed YAML. `cards/card.schema.json` is generated from the models (`make schema`), and a
test fails if it drifts.

**To change clinical content,** edit `docs/card-library.md` (or
`docs/card-library-additions.md` for Cards 7 and 8) through clinical review first, then transcribe the change into the YAML and bump the card `version`. A test checks that the
patient-facing sentences in the YAML match the library.

## 5. The matching engine and action items

`engine.match()` is pure and deterministic. For each event, in onset order:

1. **Scope.** Take the stations whose county is in `event.geography.county_fips`.
2. **Trigger.** For each card, evaluate its triggers against the event. Every evaluation is
   logged with its reason (`matched`, or why not).
3. **Size.** Look up the card's panel at each station, and skip the station if the panel
   is below `min_panel_patients`.
4. **Issue.** Create one `ActionItem` per (event, card, station, role). Roles are
   `care_team` and `patient`, plus `caregiver` when the card has caregiver text (none do
   yet). The event's temporality picks the care-team actions: a `forecast` or `imminent`
   event gets the card's `pre_event` actions, an `observed` one its `during_event` actions.
5. **Boost.** A heat or cold item in a county that also has an observed outage clearing a
   card's threshold and debounce moves up one acuity class (`profile.co_occurrence_boost`)
   and records the outage in `compounding_events`. The UI shows it as the compounding chip.
   There is no compound trigger grammar; this boost is the only way hazards combine.
6. **Supersede.** Within (card, station, role, event family), when windows overlap, the
   stronger item wins and the weaker is marked `superseded_by` it. Observed beats forecast
   or imminent, never the reverse; within the same temporality, higher CAP severity wins, so
   a Warning supersedes the Watch it follows. Hurricane/flood and power outage count as one
   family for Cards 3, 5 and 6 (`engine.SUPERSEDE_FAMILIES`), so an observed outage
   supersedes the hurricane-watch items it follows. Consecutive readings of the same outage
   never supersede each other.
7. **Rank.** Sort by acuity, then event severity, then a within-class score: the panel
   size, or for an observed outage `outage_pct × emPOWER DME count`.

**An action item** copies the card content verbatim: actions for the role, the patient
message, escalation with the templated default response, and the safety line "Don't stop
your medication — contact your care team." It also carries the event, the card id and
version, the evidence tier, citations, the panel estimate and the acuity rank. Its window
runs from `onset − card.window_days.max` to `expires`, so it opens up to 7 days before the
event. An observed event is already happening, so its item has no lead and starts at the
observation. An outage reading's item ends one second before the next poll begins, so exactly
one reading is current at any hour. Its id is its natural key,
`event_key|card_id|facility_id|role`.

**Lifecycle.**

```
issued → delivered → acknowledged → completed
   └──────────┴────────────┴──────→ expired | superseded
```

`POST /action-items/{id}/status` enforces these transitions. In live mode, `make match`
expires items whose window has ended. Re-running `match` upserts by natural key: content
refreshes, while delivery and acknowledgement progress and `created_at` are kept. Replays
are rebuilt from scratch.

**Golden tests** (`tests/golden/*.json`) pin the replay output exactly for all five
scenarios:

| Scenario | Items (superseded) | Cards that fire |
| --- | --- | --- |
| `heat_dome_2021` | 240 (132) | 1, 2, 4 across WA/OR/ID stations |
| `ian_2022` | 2,104 (260) | 3, 5, 6; hurricane-watch items yield to observed outages, dialysis ranked first |
| `uri_2021` | 2,972 (58) | 3, 5, 6 from outages, 7 from cold products, boosted where they co-occur |
| `smoke_nyc_2023` | 848 (260) | 8 |
| `smoke_canada_2026` | 2,502 (594) | 8, plus 1, 2 and 4 from heat |

To regenerate them after an intended
change, run `UPDATE_GOLDEN=<scenario> make test` (or `UPDATE_GOLDEN=all`) and review the diff.

## 6. Where the medical layer shows up in the UI

*[user-interface.md](user-interface.md) is the full, current description of every screen.
This section is only a map.*

- **Monitor (`/`)** is the one main view, live first, with the five replays in the same
  **View** menu. The medical layer adds facility circles sized by panel, **card chips**
  (one colored chip per firing card; a card keeps its color everywhere), and the side
  panel's cards firing now and facilities by acuity. Selecting a facility or a card opens its
  reading view: the clinician checklist grouped *pre-event* / *during*, the panel with
  "how was this number computed?", the emPOWER line on Card 6, the compounding chip, EAGLE-I
  attribution on outage items, the role toggle (*care team* / *patient & caregiver*), the
  **Acknowledge** and **Mark completed** buttons, and the carbon panel (§7). Card text is
  fetched from `/cards`, so no clinical wording is duplicated in JavaScript.
- **Cards (`/card-library`)**: the eight cards and where each fires (§4).
- **Scenarios (`/replays`)**: each replay, the cards it exercises, and deep links into
  Monitor at moments worth seeing.
- **Patient view (`/demo/patient-view?facility=&card=&role=`)**: a read-only rendering of
  what a patient or caregiver would receive: the verbatim card text, the safety line, the
  escalation signs and the disclaimer. It is a demo of the content. There are no patient
  accounts.

The old URLs `/playback` and `/dashboard/facilities/{id}` redirect into Monitor. In live mode
a feed-freshness banner is always shown, and an empty board is never presented as an
all-clear.

## 7. Carbon panel (display only)

`docs/carbon.yaml` holds order-of-magnitude life-cycle carbon estimates for the medications
on each card. `src/xevents/carbon.py` loads it, and `docs/carbon-footprint.md` describes the
methods. For each drug, the panel shows the assumed dose, ranges per dose and per
patient-year, a car-kilometre equivalent, the basis and confidence, and the range scaled to
the facility's panel. Drugs on one card are alternatives, so they are shown as separate
scenarios and never summed. The file's disclaimer travels with every rendering. **Carbon
never influences triggering, ranking or clinical text.**

## 8. API

| Endpoint | Returns |
| --- | --- |
| `GET /facilities[?state=&visn=&county=]` | GeoJSON of facilities with county and VISN |
| `GET /facilities/{id}` | One facility |
| `GET /facilities/{id}/panels[?card=]` | Veterans in catchment and each card's panel, with provenance |
| `GET /facilities/{id}/action-items?role=&at=` | A facility's items |
| `GET /action-items?scenario=&at=&facility=&role=&card=&status=&include_superseded=` | Compact item rows, for lists and maps |
| `GET /action-items/{id}` | One full item |
| `POST /action-items/{id}/status` | Status transition (`{"status": "acknowledged"}`) |
| `GET /cards` | The eight card definitions (reviewed content) |
| `GET /carbon` | The carbon table |

HTML pages for the cards: `/card-library` and `/card-library/{id}`. Response shapes and the
rules for rendering clinical text are in `docs/card-reference-for-frontend.md`.

## 9. Open items for clinical review

These are tracked in `PROGRESS.md`:

- The VHA-user share (0.50 of veterans), which scales every VA-literature rate.
- Heat cards also fire on heat **watches**, the 3–7-day lead signal. The card library names
  only advisories and warnings.
- Claim-level evidence tiers, and the terminology bindings (ICD-10-CM, ATC), are engineering
  placeholders. One is known to be wrong: Card 4's heart-failure mortality claim cites
  Setoguchi & Hennessy 2026, which does not contain it (see
  [medical-references.md](../medical-references.md#setoguchi--hennessy-2026--climate-change-and-medications)).
- Caregiver text is empty on all eight cards. It is content for a reviewer to write, not code.
- Notification channels (My HealtheVet, VEText, Clinical Contact Center) are named in the
  profile, but no adapters exist.
