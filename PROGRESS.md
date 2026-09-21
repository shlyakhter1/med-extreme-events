# PROGRESS

Short dated entries, newest first. One milestone per session (M0 → M5, then M6 → M10).

## 2026-09-21 — M8: emPOWER reference layer + Card 6 sub-panel

- **Source verified:** the HHS emPOWER public REST service is `HHS_emPOWER_REST_Service_Public`
  on ArcGIS Online (owner DHHS_gissupport; mirrored at geohealth.hhs.gov/dataaccess): layer 2
  county (3,233 rows), layer 1 ZIP (31,919), layer 3 state, plus per-service-type layers.
  Fields: `Medicare_Benes`, `Power_Dependent_Devices_DME`, `Facility_ESRD_Dialysis_Any_DME`,
  `O2_Services_Any_DME`, `Home_Health_Services_Any_DME`, `AtHome_Hospice_Any_DME`,
  `Any_Healthcare_Srvc_Any_DME`. No vintage field; the service's `dataLastEditDate`
  (2026-09-21) stands in and goes into the CSV `#` header with the retrieval date.
- **`scripts/build_empower.py`** → `fixtures/reference/empower_county.csv` (3,228 counties
  after dropping five FIPS-less territory aggregates) and `empower_zip.csv`; layer ids and
  field names pinned, build fails loudly on drift; raw county JSON kept, the 9.5 MB raw
  ZIP pull git-ignored. `--refresh` re-pulls. Not yet in `make reference` (manual, monthly).
- **Denominator kind:** `Denominator.empower_measure` (fourth exclusive kind) and
  `profiles/va.yaml` `empower_dme` → `power_dependent_dme`. `ReferenceTables` loads the
  county table (`load_empower` skips the header line, keeps the vintage in
  `empower_source`); `PanelEstimator.empower_dme` sums it over the station's catchment,
  unit **Medicare beneficiaries**, label "(emPOWER, measured)", caveats: Medicare proxy /
  not veteran-specific / never replaces the veteran estimate; small cells masked to 11.
  `card_panel` treats an emPOWER-keyed sub-panel as this measured component, not a share
  of the condition panel. ZIP rollup is built and loadable but the catchment rollup is by
  county (catchments are county sets); ZIP stays for provenance and a later facility view.
- **ActionItem:** `exposure` (the emPOWER estimate on outage-triggered items), `rank_score`
  and `rank_formula`. `engine.rank_for`: outage events rank by `outage_pct × empower_dme`
  (measured × measured); everything else by panel size, so existing orderings are unchanged.
  `match()` takes an optional `exposures` lookup (wired in `scripts/match.py`, the golden
  harness and tests). Store gains a `rank_score` column and orders by it within acuity; the
  dashboard board and the API compact rows use it. Golden files unchanged.
- **Card 6 v1.2.0:** sub-panel `electricity_dependent_dme` (device classes `system: empower`:
  power-dependent DME, O₂ services, facility ESRD dialysis; `denominator_key: empower_dme`),
  the addendum's care-team pre-event addition (one verbatim item), the patient-facing
  addition (verbatim) and the two escalation additions; `hhs-empower` source citation
  updated. The verbatim test now reads both reviewed documents.
- **Display:** outage-triggered items show both lines — the veteran estimate (existing) and
  "N electricity-dependent Medicare beneficiaries in catchment (emPOWER, measured; Medicare
  proxy — not veteran-specific)" — each with its own "how was this number computed?"
  popover; the exposure popover carries the ranking formula. Sub-panel components with a
  non-veteran unit print the unit and their first caveat in the panel popover.
- **Tests:** `tests/test_empower.py` — build-script row parsing on saved samples, header
  vintage, catchment rollup arithmetic, Card 6 measured sub-panel (not a share), addendum
  strings, `rank_for`, the ordering proof (larger panel loses to larger
  outage_pct × emPOWER on outage items; wins on hurricane items), and the rendered facility
  page with both denominators and provenance.
- **Next (M9):** Cards 7 and 8, cold/winter products in the NWS provider and IEM archive,
  the co-occurrence boost with `compounding_events`, profile acuity classes for cold/smoke.

## 2026-09-21 — M7: EAGLE-I outage provider (live + replay) + customer denominators

- **`providers/eagle_i.py`** with one core (`OutagePoll` → `polls_to_events`) fed by two
  paths. Events: one observed `power_outage` per (county, poll) at or above the lowest
  `outage_pct_min` any card asks for (`min_outage_pct(cards)` = 10 %), metrics
  `customers_out, county_customers, outage_pct, poll_streak, poll_minutes` (+ `feed_*`
  coverage fields from the live feed), `expires` = next poll so the engine's debounce chain
  follows consecutive polls, severity buckets by percent out (10/25/50), headline with the
  numbers, `EventSource.EAGLE_I`.
- **Live:** paged ArcGIS FeatureServer query against the EAGLE-I API fields
  (`currentOutage`, `currentOutageRunStartTime` epoch-ms, `countyFIPSCode` int → zero-padded,
  `coveredCustomers`, `modelCount`), raw snapshot cached under `fixtures/live/raw/`.
  **Finding:** FEMA's partner service `Partner/PowerOutages_EAGLE_I` returns *Token
  Required* (ArcGIS error 499) on every endpoint as of 2026-09-21 — the "no key" in the plan
  is wrong today. The client sends `EAGLEI_TOKEN` when set and raises a `ProviderError`
  that says so otherwise; `EAGLEI_FEATURE_URL` points it at any public mirror with the same
  fields. The schema was verified on two public state-EMA mirrors (Ohio watch office,
  Georgia GEMA); a 6-row sample from the Ohio one is the parser fixture. Live ingest adds
  `eagle_i` after HMS; it fails soft like the other providers and shows in the banner.
- **Replay:** streaming ORNL yearly CSV loader (`fips_code,county,state,customers_out,
  run_start_time`; early years call the count `sum` — both accepted), sliced by state /
  county / time, `resample_polls` to hourly maxima (fixture default; native 15-minute cadence
  on request), and `slice_ornl_csv` so a scenario keeps a small raw slice instead of the
  1.1–1.4 GB yearly file. The 2021 and 2025 headers were checked with range requests; no
  yearly file was downloaded (that is M10's Uri/Ian work).
- **Denominator:** `scripts/build_eaglei_customers.py` → `fixtures/reference/
  eaglei_customers.csv` (Moehl et al. MCC 2022, 3,233 counties, FIPS zero-padded, 'Grand
  Total' row dropped; 154.5 M customers) and `eaglei_state_coverage.csv` (latest EAGLE-I
  coverage share per state, 2022-01-01). Raw files (< 50 KB) are kept in git; `make
  reference` rebuilds them. `outage_pct = customers_out / customers × 100`.
- **Decision — threshold source:** the emit threshold is derived from the cards rather than
  a new `profiles/va.yaml` section; a second copy of the same number would drift. The
  profile is unchanged this milestone.
- **UI:** the event page shows customers out / county customers / percent with a "how was
  this number computed?" popover (formula, denominator source, customers≠people, ~8 %
  coverage gap) and the DOE attribution; the dashboard and events lists carry the footnote
  whenever an EAGLE-I row is shown; outage-triggered items in the facility card list carry
  the attribution and the customers≠people line, and every item now states
  `<temporality> → <phase> actions`; the playback event panel shows the outage numbers and
  attribution; `/events` JSON adds `attribution` and `caveats` to EAGLE-I events. The
  freshness banner covers the feed like every other source.
- **Tests:** `tests/test_eagle_i.py` — customer table, threshold derivation, threshold /
  metrics / streak / severity, the two-poll debounce end to end through the engine (Cards
  5/6 on the second 10 % poll, Card 3 only after two 25 % polls), FeatureServer parsing,
  paging + token + raw cache with a mock transport, the token-gated error text, ORNL slicing /
  resampling / column variants, replay events, and the rendered pages. A network-marked
  contract test (`RUN_NETWORK_TESTS=1`) parses the configured layer or the public mirror.
- **Next (M8):** emPOWER reference layer (`scripts/build_empower.py`), `empower_dme`
  denominator with county/ZIP → catchment rollup, dual-denominator display and
  `outage_pct × empower_dme_count` ranking, Card 6 `electricity_dependent_dme` sub-panel.

## 2026-09-21 — M6: temporality axis + trigger schema v2

- **`Temporality` enum** (`forecast | imminent | observed`) and a **required**
  `Event.temporality` with no default: a provider that fails to map it, or a fixture record
  without it, fails Pydantic validation (tests prove both). `ActionItem` gains
  `event_temporality` and the derived `phase`; both are in the compact `/action-items` rows.
- **Provider mapping tables are data**, raw basis kept in `metrics["temporality_basis"]`:
  NWS by CAP certainty (`Observed` → observed) else product suffix (Watch → forecast;
  Warning/Advisory/Alert → imminent; an unmapped suffix raises `ProviderError`); IEM archive
  uses the same suffix rule; AirNow `product` parameter (`observation` → observed,
  `forecast` → forecast); HMS and OpenFEMA → observed. `EventSource.EAGLE_I` added ahead of M7.
- **NWS SCN23-44 normalization** (`LEGACY_NWS_EVENT_NAMES`) runs before the accepted-set
  lookup in both the live parser and the archive parser; the legacy name is preserved in
  `metrics["raw_nws_event"]`. Cold products themselves join the accepted set in M9 (Card 7).
- **Trigger schema v2:** `outage_forecast` deleted; `temporality`, `outage_pct_min` (0–100)
  and `sustained_polls_min` (≥ 1, must accompany a metric threshold) added; schema
  regenerated; all six cards validate. Cards 5/6 fire on an observed outage ≥ 10 %, Card 3 on
  ≥ 25 %, all debounced over 2 polls; card versions bumped to 1.1.0.
- **Engine:** `phase_for` / `actions_for` derive the action phase from the event
  (forecast/imminent → pre-event + any; observed → during-event + any); a role with no
  actions in that phase gets no item. `poll_histories` builds contiguous chains per
  (source, type, geography) — a gap between one poll's expiry and the next onset resets the
  streak — and `sustained_polls_min` counts how many recent polls satisfy the thresholds.
  Supersession now ranks observed above forecast/imminent before CAP severity (never the
  reverse), and `SUPERSEDE_FAMILIES` allows observed `power_outage` to supersede
  `hurricane_flood` items on cards 3/5/6 only.
- **Decision — where streaks live:** the engine computes streaks from the event chain per
  trigger threshold (Card 3's 25 % streak differs from Card 5's 10 % streak), so a
  provider-stamped `poll_streak` (requirements §3) stays informational. The engine remains
  pure.
- **Fixtures rebuilt** from archived raw sources; the only field changes are `temporality`
  and the two new metrics, so both golden files are unchanged. Heat dome: 12 imminent, 8
  forecast; Ian: 45 imminent, 21 forecast, 1 observed (the FEMA declaration); smoke: all
  observed.
- **Schema change to the `events` table** (new `temporality` column): existing SQLite
  databases must be rebuilt (`make demo`, or `make load ingest match` against the URL);
  `create_all` does not alter tables. The Docker image rebuilds its database at build time.
- Docs: `docs/card-reference-for-frontend.md` and `docs/guide/data-sources.md` no longer
  describe the forecast-outage stub; CLAUDE.md lists the v2 docs and invariants.
- **Next (M7):** EAGLE-I provider — live FEMA FeatureServer client, ORNL historical CSV
  replay loader, Moehl county-customer denominators, `outage_pct` events, DOE attribution
  and customers≠people footnotes in the UI.

## 2026-09-21 — post-demo: design and user guide, key purged from history

- **`docs/guide/`** is the new entry point for readers. It has an index (architecture,
  quick start, configuration, guarantees) and three documents. The event layer
  (`events-and-playback.md`) and the medical layer (`medical-layer.md`) are described
  separately ahead of splitting them further. `events-and-playback.md` §7 lists every
  current coupling between the two layers. `data-sources.md` covers every external source,
  the layer that uses it, and its limits.
- **Gaps the write-up surfaced:** no provider emits `power_outage` events or a `heatrisk`
  metric, so those trigger branches on Cards 1, 2, 4, 5 and 6 are dormant. Smoke and air
  events are mapped, but no card uses them.
- **VA Facilities key removed from git history.** It had been committed in `.env.example`
  in 575fdab and removed from the tree in the next-to-last commit. History was rewritten
  with `git filter-repo --replace-text`, which puts `REDACTED` in its place, and no blob in
  the repository contains it now. The key was public before the repo went private and must
  still be **rotated** at developer.va.gov. The GitHub repo is to be deleted and recreated
  from the clean history, because a force-push leaves the old commits reachable by SHA.

## 2026-09-20 — closing an open card in playback

Opening a card in playback had no visible way out. Clicking the same row again did close
it, but nothing on screen said so, and there was no way back one level — only all the way
out, via a "show all" link buried in a section heading below the panel.

Selections nest (`card` → `facility` drill-down inside the card filter), so a single
"close" is not enough. The detail panel now carries:

- a **breadcrumb** — `All cards › <card> › <facility>` — where each earlier step is a link
  back to that level, so closing a facility returns to its card rather than to the base;
- an explicit **× close** button, labelled with its shortcut, that closes the deepest level;
- **Escape**, which does the same;
- the existing click-the-same-row-again toggle, kept because it now matches what the panel
  shows.

The breadcrumb bar is sticky, so the way out stays on screen while the panel scrolls. With
nothing selected the panel renders empty rather than holding stale content.

`make lint test`: 128 passed, including a test that the facility level closes before the
card level and that an empty selection clears the panel.

## 2026-09-20 — map colour legend

- **Both maps now carry a legend.** Counties keyed by event type (heat, hurricane/flood,
  wildfire smoke, air pollution, power outage) with the live county count beside each, the
  base colour labelled "no active event", and a note that shading deepens with severity.
  Playback adds its card key below; the dashboard adds a facility-dot key.
- **Smoke was the colour that read as "nothing".** It was a muted brown at 0.35 opacity
  against a dark base, indistinguishable from an unshaded county. It is now a warmer tan
  and the opacity floor rose from 0.22 to 0.34, so a minor alert is unambiguously shaded.
- The palette, severity ranks and legend markup moved into `web/static/map.js` so the
  dashboard and playback cannot drift apart.

**Process note, second occurrence.** Editing `playback.js` by slicing between two anchors
silently removed the whole selection block (`focusDetail`, `selectCard`, `selectEvent`,
`selectFacility`) — the page still loaded and clicks did nothing. Caught by the headless
harness, restored from git, and there is now a structural test that asserts every function
the script calls is defined. Reviewing `git diff` for unexpected deletions is the habit
this needs, not more careful slicing.

`make lint test`: 127 passed.

## 2026-09-20 — feedback round 5: honest panels, card detail visible, carbon panel

- **Cards were firing at every facility in a county, inflating the panels several-fold.**
  Panels live at the station that owns a catchment and clinics inherit that estimate for
  display, but action items were being issued at the clinics too, so the same estimated
  patients were counted once per facility. In the heat-dome replay that produced 70
  facilities holding only **14 distinct panel values**, summing to 102,791 estimated
  lithium patients. Action items are now scoped to the 183 panel-owning stations
  (`PanelEstimator.owns_panel`), so every panel is counted once: 11 stations, 11 distinct
  values, 13,956. Ian's dialysis panel now sums to 3,872 of the 52,000 national count,
  which is a plausible Florida share. Replay items fell from 1,608 to 240 (heat dome) and
  3,122 to 352 (Ian); live from 10,352 to 1,232. Golden files regenerated, and a new test
  asserts no two facilities report the same panel for the same card.
- **A card must imply at least one patient.** `profile.min_panel_patients` (1.0) stops a
  card firing where the estimate is a fraction of a person; the engine logs the skip with
  the computed panel so the decision is auditable.
- **Card detail was rendering where nobody would find it.** The detail panel sat at the
  bottom of a 21,000-character side panel, below roughly 60 rows — the content was always
  there, just past the fold. It now renders directly under the "as of" summary at the top,
  and selecting anything scrolls the panel to the top.
- **Patient and caregiver are one audience.** The three-way role toggle became two:
  *care team* and *patient & caregiver*, with caregiver wording shown beside the patient
  text (and a note where it has not been written yet). The data model still carries all
  three roles; this is presentation only.
- **Carbon panel.** `docs/carbon.yaml` (schema and loader in `src/xevents/carbon.py`,
  methods in `docs/carbon-footprint.md`) is exposed at `GET /carbon` and rendered per card
  in both the facility page and playback: assumed dose, per-dose and per-patient-year
  ranges, a car-kilometre equivalent, basis and confidence, and the range scaled to that
  facility's estimated panel. Drugs on a card are alternatives a patient takes one of, so
  rows are shown as separate scenarios and never summed, and the file's own disclaimer
  travels with every rendering. Carbon is display-only: it does not touch triggering,
  acuity or any clinical content.

`make lint test`: 125 passed. Image 349 MB.

## 2026-09-20 — feedback round 4: card detail and card symbols in playback

- **Selecting a card now shows the card.** Previously it only filtered the map. The panel
  now renders the card itself: summary, acuity class, evidence tier, the 3–7 day window, a
  care team / patient / caregiver toggle with the reviewed text, the profile-templated
  safety line and escalation triggers, the citations, and the facilities it is firing at
  with their locations and panel sizes. Card text is read from `GET /cards` (the card
  library) and the templated escalation/safety line from one sampled action item, so no
  clinical or profile wording is duplicated in JavaScript (CLAUDE.md constraint 4).
- **Cards have their own map symbol.** Facilities stay circles (a place); cards are drawn as
  a small fanned stack of coloured chips above the facility, one chip per card, which reads
  as a playbook card and cannot be confused with the facility dot or the weather shading.
  Selecting a card enlarges its chip and hides the rest. Colours key off the card's number
  in the library, so a card keeps its colour across views. A clickable legend sits on the
  map, and badges are diffed per facility so playback stays smooth.
- Panel precedence: clicking a facility while a card filter is on keeps the filter but shows
  the facility; clicking it again returns to the card.

**Process note.** Two template edits failed silently because their anchor text had already
changed, so the badge CSS shipped missing and the badges rendered invisible. Anchored edits
now assert; the headless harness (`node` + a DOM stub) was extended to click a card and
assert the detail panel and the badge markers actually render, which is what caught it.

`make lint test`: 115 passed.

## 2026-09-20 — feedback round 3: cards everywhere, live window, locations, navigation

- **Live is now the trailing two weeks, not just this instant.** `api.weather.gov/alerts/active`
  reports only what is in force right now, so the live view emptied out whenever the weather
  was calm. `IEMArchiveProvider` backfills the same NWS products from the Iowa State VTEC
  archive (`--lookback-days`, default 14): 683 archived events plus 77 currently active, 44
  duplicates dropped by matching product name, counties and onset hour. 731 events → 10,502
  action items. Events stay `source=nws` because they are NWS products;
  `metrics.retrieval` records that they came from the archive.
- **Cards are surfaced in playback, not just on the dashboard.** New "Cards firing now"
  panel listing each card with the facilities it covers, what triggered it, its acuity class
  and its largest panel. Cards were always being generated in replay; they were simply
  invisible until you clicked a facility.
- **Cards are on the map.** Selecting a card filters the map to the facilities where it
  fires and recolours them by card, so the map answers "where is this card firing?" as well
  as "what weather is happening?". Facility tooltips name the cards and the panel size.
- **Getting back to live from playback.** The playback view selector now offers
  `live (now) — last 2 weeks` alongside the replays, the header carries Dashboard and Events
  links that preserve the chosen view, and the dashboard links into playback for the same
  view. `/playback?scenario=` round-trips.
- **Location and timestamp on everything.** Events show where (CAP area description, else
  states and county count) and their window in UTC; facilities show city, state and VISN;
  cards show their window. Added as a "Where" column on the dashboard and events tables, and
  as sub-lines on every row in playback.

**Performance.** With 733 events the timeline was rebuilding 226 KB of SVG on every tick.
Bars are now drawn once per view or selection change and only the playhead moves per tick.

`make lint test`: 113 passed.

## 2026-09-20 — follow-up: "no events, live or playback"

Three separate causes, all fixed.

- **Live mode was genuinely empty.** The demo container ships with the replay scenarios
  only; the live events previously seen lived in a Postgres database that was removed during
  the Docker cleanup. Live ingestion now runs inside the container
  (`docker exec -e EVENT_MODE=live mee python scripts/ingest.py --mode live`, then `match.py`),
  giving 87 real events and 664 action items alongside the replays. `docs/deploy.md` §4
  covers doing this on a schedule when hosted.
- **A stale cached 404 could blank the playback page.** `/static/map.js` 404'd in the window
  before `StaticFiles` was mounted; a browser that cached that leaves `XMap` undefined and the
  page silently empty. Static URLs now carry `?v=<asset mtime>`, `playback.js` checks its
  dependencies and prints a plain-language error instead of rendering nothing, and the whole
  page is rendered through Jinja so the version reaches the template.
- **`event_key` was missing from the events API.** It is a Python `@property`, so
  `model_dump()` drops it, which broke event selection and the "open full event page" link in
  playback (the server-rendered pages were fine because Jinja reads the property directly). A
  Pydantic `computed_field` would have been the obvious fix but breaks round-trip validation
  under `extra="forbid"`, which the replay fixtures and the event store both rely on, so the
  key is re-attached at the API edge in `event_json()`.

**Also:** Leaflet and htmx are now vendored under `web/static/vendor/` instead of loaded from
unpkg.com, so the demo has no external runtime dependency at all — it renders offline, behind
a firewall and in an air-gapped container. A test asserts no page references a CDN.

`make lint test`: 109 passed. Image rebuilt at 382 MB and verified serving live + replay.

## 2026-09-20 — demo feedback round: run/host docs, event exploration, timeline, key-free map

Four issues raised after walking through M5, all fixed and covered by tests.

- **"bad timestamp" on every page.** The header form submitted `+00:00`, and `+` is the URL
  encoding for a space, so the app rejected the as-of value it had just rendered. The control
  is now `<input type="datetime-local">` (no offset, so no `+`), and `timeparse.parse_at`
  accepts the space-for-plus form, a trailing `Z`, minute precision and a bare date. Naive
  values are read as UTC. Regression test covers all five spellings.
- **Events were not explorable.** New `/dashboard/events` (window, severity, county and
  facility counts, active-vs-all toggle) and `/dashboard/events/{key}` (counties on a map,
  UGC codes, CAP metrics, raw payload path, the action items it produced). The dashboard
  gained an active-events table, and both banners now state that times are UTC and whether
  the feed is live or replayed. API gained `GET /events/detail?key=`.
- **Playback had no timeline and pause did not hold.** Rewritten: an SVG timeline with one
  lane per event type, a bar per event across its active window, day gridlines, a playhead,
  click/drag to seek and click-a-bar to inspect. Transport uses an explicit `playing` flag
  with step buttons, spacebar and arrow keys. The old version refetched facility detail on
  every tick, which is what made it look like it resumed on its own; nothing fetches during
  playback now and county/facility repaints are diffed.
- **Map demanded an API key.** Both maps used CARTO raster tiles, which watermark
  unregistered use. `web/static/map.js` now draws the county polygons the app already serves
  at `/reference/counties`. No third-party tile request, no key, works offline.

**Packaging and hosting** (the other half of the feedback): `requirements.txt` generated from
the lockfile with pinned hashes for pip users; `Dockerfile` that bakes the demo database at
build time (verified: 381 MB image, serves every page with no key, no database server and no
network); `fly.toml`; `docs/deploy.md` covering local, container, Fly/Render/Cloud Run, live
mode with a writable volume and a refresh schedule; README rewritten to lead with how to run
it. `make lint test`: 107 passed.

**Incident note.** The first Docker build filled the host disk, which wedged the Docker
daemon (a stale `com.docker.backend` from Sep 10 survived restarts and had to be killed).
Pruning images and build cache reclaimed 55 GB inside Docker; its virtual disk shrank from
83 GB to 1.5 GB and the host went from 5.7 GB to 87 GB free.

## 2026-09-20 — M5: API + UI (done)

**Done.**
- Server-rendered pages (Jinja2 + htmx, `src/xevents/web/views.py` + `templates/`):
  - `/` **dashboard**: header with scenario switcher (three replays + **live (now)**) and an
    "as of" time; replay defaults to the scenario's peak hour (`/scenarios` → `peak_at`);
    event board ranked by acuity, then severity × panel (stations before clinics on ties);
    outreach queue count for unacknowledged high-acuity items; Leaflet map of facilities
    colored by active event and sized by panel; live mode shows a **feed-freshness banner**
    (`/feeds`: per-source count, last ingest, stale > 6 h) and never renders an empty board
    as an all-clear.
  - `/dashboard/facilities/{id}` **drill-down**: fired cards (strongest event per role),
    clinician checklist grouped pre-event / during, panel with expandable "how was this
    number computed?" (formula, components, caveats, sources), role toggle via htmx
    (care team / patient / caregiver), event id + card version + evidence tier + citations
    on every card, **Acknowledge / Mark completed** buttons posting to the status machine.
  - `/demo/patient-view?facility=&card=&role=` read-only patient/caregiver rendering of the
    same action items (verbatim card text, safety line, escalation triggers, disclaimer).
- `make demo`: fresh SQLite DB → reference + catchments → three replays → action items →
  serves the dashboard and opens it (no network needed; ~1 minute).
- Live mode verified end to end on the Postgres DB: `EVENT_MODE=live make ingest match`
  ingested real NWS/OpenFEMA/HMS events and the dashboard rendered them with the banner.
- `make lint test`: green.

**Success criteria (docs/implementation-plan.md §1), as verified through the pages.**
1. Heat dome replay: Cards 1/2/4 for WA/OR facilities with sized panels and clinician +
   patient content — dashboard at the peak hour lists 68 facilities / 708 open items;
   Portland VAMC page shows all three cards. ✔
2. Ian replay: Cards 3/5/6 for Florida; dialysis ranked first (acuity rank 0). ✔
3. `EVENT_MODE=live` ingests real feeds with no code change and the live dashboard renders
   whatever is active, with freshness. ✔ (AirNow still needs a key.)
4. Traceability: every panel number expands to its formula/inputs/sources; every card shows
   its event id, card id + version, evidence tier and citations. ✔
5. `make demo` rebuilds from empty in one command. ✔

**Not done / next.** Notification channel adapters remain stubs (out of scope). Caregiver
content is empty pending reviewed text. AirNow response shape unverified without a key.
Recorded run-through of the demo script is the user's to do.

## 2026-09-20 — M4: matching engine + action-item store (done) + playback view

**Done.**
- `engine.py`: pure `match(events, cards, facilities, profile, panels, now)` → one
  `ActionItem` per (event, card, facility, role), acuity-ranked; every trigger evaluation is
  logged (event, card, matched / why not). Facilities in scope = facility county ∈ event
  counties; triggers = card `event_triggers` (NWS product names, HeatRisk, AQI, FEMA,
  outage). Within (card, facility, role, event type) the strongest overlapping event wins
  and weaker items are marked `superseded_by` it.
- `ActionItem` model per requirements §7 with card content copied verbatim (actions,
  patient message, escalation with the profile's templated default response, safety line,
  evidence tier, sources, panel estimate, window = onset − card.window_days.max → expires).
- Store: `action_items` table; upsert by natural key keeps delivery/acknowledgement
  progress and `created_at`, applies/lifts supersession; status machine
  issued→delivered→acknowledged→completed|expired|superseded (`transition_action_item`,
  `expire_action_items`). `make match` (replay: all scenarios; live: now + auto-expire).
- Golden tests (`tests/test_golden.py`, `tests/golden/*.json`): heat dome 2021 → 1,608
  items (720 issued, 888 superseded) across 70 WA/OR/ID facilities, Cards 1/2/4 only,
  Portland + Seattle + American Lake included; Ian 2022 → 3,122 items across 81 FL
  facilities, Cards 3/5/6 only, dialysis ranked first. Re-runs are byte-identical;
  supersede path covered in `tests/test_engine.py`. Regenerate with `UPDATE_GOLDEN=1`.
- API: `GET /scenarios`, `GET /events?scenario=&at=&county=`, `GET /events/active`,
  `GET /action-items?scenario=&at=&facility=&role=&card=&status=` (compact rows),
  `GET /action-items/{id}`, `POST /action-items/{id}/status`,
  `GET /facilities/{id}/action-items?role=&at=`, `GET /cards`, `GET /reference/counties`,
  gzip middleware.
- **Playback view** (`/playback`, from `docs/playback-view.md`): Leaflet map, county layer
  colored by the most severe active event, facility markers sized by affected panel, a
  time scrubber with play/pause and speed, an acuity-ranked event board, and a facility
  drill-down with fired cards, sized panels ("how was this computed?" provenance), role
  toggle (care team / patient / caregiver), verbatim card text, safety line, escalation.
  `make serve` then open http://localhost:8000/playback.
- Connecticut: `fixtures/reference/ct_legacy_county_crosswalk.csv` (legacy county →
  planning regions by grid-sampled area share, builder `scripts/build_ct_crosswalk.py`);
  `UgcResolver` translates NWS legacy CT codes, so CT alerts now match facilities.
- `make lint test`: green.

**Decisions.**
- Heat cards now also fire on `Excessive Heat Watch` / `Extreme Heat Watch`: the watch is
  the 3–7-day lead signal the cards are designed around (the library names the advisory
  and warning only). **Confirm with the clinical reviewer.** Watches are superseded by the
  warnings that follow, so the map shows the escalation.
- OpenFEMA declarations are context, not triggers (no card lists them), matching
  requirements §4.
- Caregiver items are generated only when a card has caregiver content (none in v1).
- Item volume is high (a warning over 20 counties × 3 cards × 2 roles × facilities); the
  compact `/action-items` rows keep the playback page responsive; detail is per item.

**Next:** M5 — dashboard/event board and patient view as server-rendered pages sharing the
playback's API; scenario switcher + live toggle; `make demo`.

## 2026-09-20 — M3: denominators (done)

**Done.**
- Reference tables: `fixtures/reference/places_county.csv` (CDC PLACES 2025 county release,
  10 measures) and `vetpop_county.csv` (VetPop2023 Table 9L, 2023–2030 projections) with
  builders `scripts/build_places.py` / `build_vetpop.py` (new deps: `openpyxl` to read the
  VetPop workbook, `types-openpyxl` for mypy).
- Catchments (`geography/catchment.py`): county → nearest anchor station (VAMC/HCC);
  non-anchor facilities map to a station by health care system (else nearest). Persisted in
  `county_catchment` and `facility_station` tables by `make load`.
- `denominators.py`: `ReferenceTables` + `PanelEstimator` producing `Estimate` objects
  (value, formula, inputs, sources, caveats, components). Rate paths: VA-literature rate on
  the `vha_users` scope, national count allocated by veteran share, PLACES county rate;
  card panels add profile class shares (`panel_multipliers`) and sub-panels (Card 3).
- `GET /facilities/{id}/panels[?card=]` returns sized panels with provenance.
- National sanity anchors in the profile, checked by `make load` and a test: veterans total
  vs VetPop 17,260,286 (±5%), heart-failure panel vs ~510k VHA HF patients (±20%).
- `make lint test`: green. Example: Portland VAMC ≈ 84k veterans in catchment (9 counties); Card 4
  panel ≈ 1.3k.

**Decisions.**
- Anchors are stations, not clinics: with CBOCs as anchors, most VAMCs received no
  counties (a CBOC is usually nearer to a county centroid), which broke the demo's
  "Portland VAMC with sized panels". Panels live at the station; clinics inherit.
- VA-literature rates ("of VHA enrollees / VA patients") are applied to veterans × 0.50
  (`scopes.vha_users`, VHA enrollees ≈ 9.1M / 18.3M veterans). Without this, HF came out
  at 855k vs the 510k anchor. **The 0.50 share needs verification before real use.**
- PLACES 2024/2025 have no CKD measure; the plan's CKD column is dropped (no v1 card sizes
  on CKD; it is a Card 1 risk flag only).
- VetPop territory rows are spread evenly over the territory's counties (PR ≈ 69k veterans
  over 78 municipios); "Foreign Countries" is excluded from `national_veterans`.
- Connecticut: VetPop, PLACES and the Census 2023 boundaries all use the 2022 planning
  regions (09110–09190), but NWS SAME/UGC codes use legacy counties (09001–09015). **M4
  needs a CT legacy-county → planning-region crosswalk** or CT alerts will not match.

**Also:** `docs/playback-view.md` drafts the map playback (time scrubber over a scenario)
for M5.

**Next:** M4 matching engine + action-item store.

## 2026-09-20 — M2: event providers + replay scenarios (done)

**Done.**
- CAP-derived `Event` model (source, type, CAP severity/urgency/certainty, onset/expires,
  geography keys: county FIPS, UGC, ZIPs, polygon; metrics; scenario; raw_ref) and an
  `events` table with upsert by natural key `source:source_id` (`store.py`).
- Providers (`providers/`): `NWSAlertsProvider` (api.weather.gov `/alerts/active`, SAME +
  UGC → counties via the NWS zone-county correlation file), `OpenFEMAProvider`
  (declarations grouped per disaster, county rows), `HMSSmokeProvider` (daily shapefiles →
  one event per day × density, counties by approximate polygon coverage), `AirNowProvider`
  (`/aq/data/` monitoring-site bbox endpoint from AirNow's retained list; monitors →
  counties by point-in-polygon), `ReplayProvider` (fixture `events.json`).
- Reference: `fixtures/reference/nws_zone_county.csv` (NWS bp16ap26.dbx, 4,848 rows) built
  by `scripts/build_nws_zones.py`.
- Three replay scenarios built from archived real data with per-scenario `build.py` and raw
  files kept in git (`fixtures/events/README.md` has provenance and gaps).
- `make ingest` (`scripts/ingest.py`): `EVENT_MODE=replay` loads all three scenarios
  (96 events) — verified into SQLite and the compose Postgres; `EVENT_MODE=live` ingested 87
  real events (78 NWS, 3 OpenFEMA, 6 HMS) into the same table. `make scenarios` rebuilds.
- `make lint test`: green.

**Findings / corrections.**
- api.weather.gov keeps no alert history (2021/2022 windows return empty), so archived
  alerts come from the Iowa Environmental Mesonet VTEC archive (`watchwarn.py` CSV), parsed
  by `providers/iem_archive.py` into the same Event model.
- NWS renumbered WA/OR/ID public zones after 2021; the current zone-county file lacks
  e.g. ORZ006/WAZ558. Dated zone geometries from IEM (`/api/1/nws/ugcs.geojson?valid=`)
  are intersected with county polygons to resolve them (heat dome: 129 counties, 0
  unresolved). Same for two 2022 FL zones.
- NWS Air Quality Alerts are non-VTEC and absent from the archive; the smoke scenario is
  HMS-only. The live provider tracks "Air Quality Alert".
- AirNow: the detailed endpoint docs are login-gated. The provider targets `/aq/data/`
  ("Observations by Monitoring Site", in the retained 2026 list) rather than the retiring
  ZIP/lat-long observation services. **Response shape unverified until a key exists** —
  first live run should be checked against `fixtures/live/raw/airnow_data_*.json`.
- `NWS_USER_AGENT` in `.env` is still empty; the live run used a repo-URL contact string
  passed on the command line. Set it in `.env` for `make ingest` live.
- No new dependencies (pyshp reused for HMS shapefiles).

**Next:** M3 denominators (CDC PLACES county measures × VetPop × profile multipliers).

## 2026-09-20 — M1: facility spine + geography (done)

**Done.**
- `Facility` model; VA Facilities **v1** client (`providers/va_facilities.py`) with paging,
  raw-page caching, JSON:API → GeoJSON conversion; parser tested against a hand-written v1
  page sample derived from the public OpenAPI document, plus a mocked two-page pull.
- ZIP → county crosswalk fixture (`fixtures/reference/zip_county.csv`, 33,791 ZIPs) built
  from the Census 2020 ZCTA↔county relationship file; HUD USPS used automatically when
  `HUD_API_TOKEN` is set. Loader + attribution (`geography/`) with an unresolved report.
- SQLAlchemy store (`store.py`, SQLite fallback or Postgres) with upsert by facility id;
  FastAPI `GET /health`, `GET /facilities[?state=&visn=&county=]` (GeoJSON), `GET /facilities/{id}`.
- `make reference` (build fixtures), `make load` (attribute + persist, exit 1 if any facility
  lacks county/VISN), `make serve`. Network contract test is `@pytest.mark.network`, skipped
  without the key.
- Live pull done with the user's key: **1,400 health facilities** from `sandbox-api.va.gov`
  (self-service keys are sandbox-only; the builder retries against sandbox on a production
  401). Cached to `fixtures/reference/facilities.geojson` with raw pages.
- County attribution switched to **point-in-polygon** on facility coordinates against Census
  1:5m county boundaries (`fixtures/reference/counties.geojson`, builder
  `scripts/build_county_boundaries.py`, new dep `pyshp` to read the shapefile), with the ZIP
  crosswalk as fallback. ZIP-only missed 22 facilities including seven VAMCs on institutional
  ZIPs (15240, 23249, 84148, …) that are not ZCTAs; the 1:20m boundary file omits Guam and
  other territories, hence 1:5m.
- **Done when verified:** 1,399/1,400 facilities resolve to county + VISN; the sole exception
  is `vha_358` Manila VA Clinic (Philippines, no US county), pinned by a golden test
  (`test_m1_done_when_every_health_facility_resolves`). Loaded into both SQLite and the
  docker-compose Postgres.
- `.env` support: every `make` target passes `--env-file .env` to `uv run` when the file
  exists; `.env.example` defaults `DATABASE_URL` to SQLite.
- `make lint test`: green.

**Findings / corrections.**
- Facilities API v0 is gone (`/v0/facilities/all` → 404). v1 has no `/facilities/all` and no
  GeoJSON media type; the plan's "must request GeoJSON or CSV" note was v0-era. CLAUDE.md
  constraint 6 updated. The `search-va-facilities-api` skill's v1 base path was right.
- data.va.gov `9hbf-9jzg` (VISN/market/county) is a broken FY2017 blob; no tabular substitute
  found. VISN comes from the facility record; **market attribution is not available** (a
  `market` column exists, left null). Revisit if a source turns up.
- HUD crosswalk needs a token; Census ZCTA fallback documented with its caveats in
  `fixtures/reference/README.md`.
- Deprecation warnings from starlette's TestClient about httpx are upstream noise.

**Next:** M2 event providers (NWS alerts, AirNow, HMS smoke, OpenFEMA, replay) and the three
fixture scenarios. The county boundary index built here can serve HMS polygon → county
intersection if PostGIS friction appears.

## 2026-09-20 — M0: scaffolding + card library (done)

**Done.**
- Repo scaffolded at `medtask/med-extreme-events/` per `docs/implementation-plan.md` §2;
  planning docs moved from `medtask/docs/` into `docs/`; `CLAUDE.md` at repo root; `git init`
  (no commits yet).
- Tooling: `uv` + `pyproject.toml` (Python 3.12, hatchling), `Makefile` (`lint`, `test`,
  `schema`, `skills`, `skills-check`, `db-up/down`; `ingest`/`demo` stubbed until M2/M5),
  `docker-compose.yml` (postgis/postgis:16-3.4), GitHub Actions CI (`make lint test`).
- Card schema as Pydantic v2 models in `src/xevents/models.py`; `cards/card.schema.json`
  is generated from them (`make schema`) and a test fails if it drifts.
- Six cards transcribed to `cards/0N-*.yaml`. Patient-facing sentences are verbatim from
  `docs/card-library.md` and a test enforces that.
- `profiles/va.yaml`: denominator anchors, acuity order, channels, hooks, default escalation
  template. Cards reference profile keys; a test checks every reference resolves.
- Loader (`src/xevents/cards.py`) rejects: unknown fields, untiered claims, a `weak` tier,
  unknown source ids, duplicate ids/numbers, medication cards without
  `safety.do_not_stop_medication: true`, and malformed YAML — each with a file-anchored
  message. Six malformed fixtures under `tests/fixtures/cards/invalid/`.
- Data-source skills reused from `../../nyc2026-dataset` without copying: `make skills`
  symlinks a curated subset into `.claude/skills/`; verified with a headless `claude -p` run
  that all seven are discovered. `--add-dir` documented as the way to get the full set.
- `make lint test`: green (ruff, ruff format, mypy --strict, 29 tests).

**Decisions.**
- `event_trigger` (singular, in the plan) became `event_triggers: [...]` — any listed
  trigger fires the card. Needed because Cards 5/6 fire on hurricane *or* forecast outage.
- Evidence tiers are `strong | inferential | expert_guidance` (requirements §8). `weak` is
  not representable, so weak/folklore claims cannot be published. Claim-level tiers were
  assigned per the card library's own tier definitions (case reports and non-significant
  subgroups → `inferential`); card-level `evidence_tier` must match the tier of at least one
  claim. **Needs clinical reviewer confirmation.**
- Heat triggers list both `Excessive Heat Warning` (pre-2025 NWS name, used by the 2021
  heat-dome fixture) and `Extreme Heat Warning` (current name).
- Terminology bindings: conditions as ICD-10-CM, medication classes as ATC, devices as
  `local`/`empower` codes. Engineering placeholders for M3/M4 selectors — **not clinically
  reviewed**.
- `actions.caregiver` is empty on all six cards: the card library has no caregiver-addressed
  text and we do not author clinical language in code. Requirements §6 says caregiver mode
  is "the same content addressed to the caregiver"; treat as content-authoring work for a
  reviewer, or a rendering rule in M5 with a profile-templated preamble.
- New dependencies (all boring, per constraint 7): runtime `pydantic`, `pyyaml`, `fastapi`,
  `uvicorn`, `sqlalchemy`, `psycopg[binary]`, `httpx`, `jinja2` (the §2 stack); dev
  `pytest`, `ruff`, `mypy`, `types-PyYAML`, `jsonschema` (validates cards against the
  checked-in JSON Schema so the file is real, not documentation).

**Risks / follow-ups for M1.**
- `search-va-facilities-api` skill documents base path `services/va_facilities/v1`; the plan
  says v0 with `/facilities/all` GeoJSON. Verify with a real key before writing the client.
- Denominator numbers in `profiles/va.yaml` are the card library's planning anchors; M3
  replaces/augments them with PLACES × VetPop.

**Next:** M1 — facility spine + geography (VA Facilities API client, VISN/Market/County
crosswalk, HUD ZIP↔county, cached pulls into `fixtures/reference/`).
