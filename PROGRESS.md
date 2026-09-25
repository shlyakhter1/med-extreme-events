# PROGRESS

Short dated entries, newest first. One milestone per session (M0 → M5, then M6 → M10, then
M11 → M12 from `docs/implementation-plan-clinical.md`).

## 2026-09-25 — nor'easter gap: coastal-flood and wind triggers

**Why.** In live mode a nor'easter produced no flood items. The NWS provider dropped every
product outside `NWS_EVENT_TYPES`, and a nor'easter issues Coastal Flood and High Wind
products (Storm Surge is tropical-only). The live feed on 2026-09-25 had 30 Coastal Flood
Warnings (CT–NC) and High Wind Warnings (DE, MA, NJ, RI), and none of them reached a card.

**Done.** `make lint test` green (321 passed, 9 skipped); goldens unchanged (the scenario
fixtures were retrieved filtered to their own VTEC phenomena).
- Card library first: Card 3 triggers add Coastal Flood Watch/Warning and Flash Flood Watch.
  The provider already mapped Flash Flood Watch, but no card listed it, so it never matched.
  Cards 5/6 add High Wind Watch/Warning and Extreme Wind Warning. Advisories (Coastal Flood,
  Wind, Flood) are deliberately not tracked. The change is recorded as open question 6 for
  clinician sign-off; no card text changed. Versions: Card 3 2.1.0, Card 5 1.3.0, Card 6 2.1.0.
- **Decision:** new `EventType.HIGH_WIND` (a forecast of outage risk), not a reuse of
  `power_outage`, which stays observed-only EAGLE-I data. Cross-family supersede pair
  `(high_wind, power_outage)` on Cards 5/6 in `engine.SUPERSEDE_FAMILIES`. There is no
  co-occurrence boost pairing for wind.
- IEM archive: VTEC CF.A/CF.W/HW.A/HW.W/EW.W mapped and added to the live backfill phenomena.
- Map/playback get a `high_wind` color. Schema and card-facts table regenerated.
- New guard (`tests/test_engine.py::test_noreaster_triggers`): every tracked NWS product
  except Air Quality Alert must be listed by some card.

**Next.** Redeploy so the live instance picks this up. Clinician to confirm that the
hurricane-framed Card 3/5/6 text fits nor'easter/wind events.

## 2026-09-23 — review status corrected; clinician sign-off questions

The 2026-09-23 card-library revision was drafted by Claude, not by a clinician. The docs,
card YAML headers, `CLAUDE.md` and the Cards page had called it "clinically reviewed"; they
now say **AI-drafted, pending clinician sign-off**. `docs/card-library.md` opens with a
status section and five open questions for the clinician: the Card 6 mechanism sentence,
the Card 4 panel figures, card-level tiers, caregiver text, and the ten pending sources (plus
the four VA anchors). The clinician's files are `docs/card-library.md` and
`docs/medical-references.md` §1/§3/§4/§5. The text of all eight cards is unchanged.

## 2026-09-23 — M12: consistency guards, phase handling, provenance polish (done)

**Done.** `make lint test` green (317 passed, 9 skipped). Goldens regenerated with
`UPDATE_GOLDEN=all`: **zero diff** in all five scenarios. The review changed text, versions
and source ids only, which is what the plan requires. The `make demo` pipeline runs clean from an empty
DB (run against a scratch DB so the local `demo.db` was left alone); the card, facility and
patient pages were smoke-tested against it.
- `tests/test_clinical_consistency.py` covers medical-references §3. The fluid-limit sentence
  is byte-identical on Cards 1/4/6 and the CO sentence on 5/6/7/8; Card 8 has the
  cleaner-air/cooling escape hatch and Card 7 the insulin-freeze line; Card 1's patient text
  has no liters-per-day figure; and no patient/caregiver string or safety line tells anyone
  to stop, hold, skip or change "your …" (negated forms are allowed). The shared sentences
  are read from §3 itself, not restated. **Mutation-checked:** 12 parametrized
  perturbations, and each one must trip its guard.
- Post-event action: **option A** shipped. Card 1's "After the event: …" is a
  `during_event` care-team item, and the YAML has a comment explaining why. Option B
  (`post_event` phase) is written up as a backlog entry in `docs/requirements-v2.md` §9.
- Provenance: `Estimate.kind` (`planning_estimate | modeled_estimate | measured`), with
  `EstimateKind` in models. The estimator sets it (rate/count/share → planning; PLACES →
  modeled; emPOWER → measured; lower-bound and upper-bound panels inherit it). Planning
  panels also carry `PLANNING_CAVEAT`. The popover and stat line render the label.
  `profiles/va.yaml` sources now name their `va-*-prevalence` anchor ids. No data or number
  changed.
- Hotlines: a `tel_links` Jinja filter escapes the text and wraps only the phone digits in
  `tel:` links. It is applied to patient and caregiver text (card page, patient card) and to
  hook phones. Card 6 renders KHARES and legacy KCER as two links. The `kcer_hotline` hook
  now names KHARES and has a `TODO(2026-Q4)` to drop the legacy number, and so does the
  card YAML.
- Contested findings: the card page renders `evidence.caveats` (verified); tests pin Card 2's
  contested mechanism and Card 6's borderline survival signal on the page.

**For the clinical reviewer.**
- Card 6 has no mechanism paragraph in the reviewed library. `evidence.mechanism` is
  required, so the v1 sentence ("Disasters cut transportation, power, and water …") was
  kept, with a YAML comment. Card `summary` fields are sentences quoted from each card's
  library text (Card 6's is its Katrina magnitude sentence).
- The HFrEF ACE/ARB/ARNI share (0.62), which narrows Card 4's panel, and the ~510,000 VHA
  HF national anchor come from the v1 library and are not restated in the review. They were
  kept, so panels and goldens do not change, and they are labeled planning estimates.
- Card-level `evidence_tier` values are unchanged: Card 3 stays `inferential`, although
  most of its claims are now `strong`. The library assigns tiers per claim only.

**Next:** after one green release, delete `REMOVED_SOURCE_IDS` and its test in
`tests/test_cards.py`. Then the verification queue (medical-references §5) and caregiver text,
both reviewer work.

## 2026-09-23 — M11: adopt the reviewed card library (done)

**Done.** `make lint test` green.
- `docs/card-library.md` and `docs/medical-references.md` were replaced by the AI-drafted
  review versions (Claude; not yet signed off by a clinician), and `docs/card-library-additions.md` was deleted (merged). Inbound links were
  fixed in the guide, requirements-v2, implementation-plan-v2, CLAUDE.md and `carbon.py`. A
  new test checks that every relative link in `docs/`, README and CLAUDE.md resolves
  (47 links). The library header now documents the transcription rule: `[SHARED]` and
  `[tier | ids]` markers and `*emphasis*` are stripped.
- **All eight cards re-transcribed** from the library. The plan assigned this to the
  maintainer; it was done here so the suite could go green. **It needs a maintainer diff
  review.** Patient, care-team, escalation, claim and caveat strings are verbatim, and a test
  now enforces all five against the library, not just patient text. Triggers, selectors,
  `window_days`, acuity and hooks are untouched. Versions: 1/3/4/6 → 2.0.0; 2 → 1.1.0;
  5 → 1.2.0; 7/8 → 1.1.0.
- Source ids migrated to the new index. `setoguchi-hennessy-2026` is now cited only on
  Card 5, which fixes the known-wrong Card 4 claim. Card 8's July-2026 replay-context claim
  and its four news sources are gone, because they are not in the reviewed library. Tests:
  every cited id is in §1; each card's ids equal its §2 row exactly; no figure-bearing claim
  rests only on `pending` sources (§1 status parsed; "PM2.5" is not a figure); a temporary
  `REMOVED_SOURCE_IDS` guard; no string or page contains `[SHARED]`.
- `docs/card-reference-for-frontend.md` now has a per-card facts table generated from the
  YAML (`make card-docs`, `scripts/card_docs.py`), with a freshness test. Stale hand counts
  were removed, and the Card 6 note now covers both hotlines.
- Claim tiers come from the AI-drafted review (pending clinician sign-off); the "engineering
  placeholders" caveat was removed from the guide and marked superseded in the M0 entry.


## 2026-09-23 — guide review; medical references

**Done.** `make lint test` green (288 passed, 9 skipped).
- `docs/guide/medical-layer.md` covers all eight cards (triggers incl. observed outages, lead
  windows, sub-panels, full acuity order), the v2 engine rules (phase from temporality,
  co-occurrence boost, supersede families, outage ranking, no lead for observed events) and
  per-scenario golden counts; §6 now maps the current UI instead of the retired pages. The
  other four guide pages were checked against the code and corrected (keyless AirNow,
  EAGLE-I, cold products, the About screen, live refresh, new reference layers).
- `docs/medical-references.md`: the 42 sources the cards cite, card by card (a test fails if a
  card cites an id the index lacks), and a verified entry for Setoguchi & Hennessy 2026
  (Pharmacoepidemiol Drug Saf 35(8):e70437, doi:10.1002/pds.70437, PMC13427620).

**For clinical review.** Card 4's claim "Extreme heat above the 97th–99th temperature
percentiles is linked to roughly a 10–15% rise in HF-related deaths" cites only
`setoguchi-hennessy-2026`, and the commentary contains no such figure (full text checked via
Europe PMC). `card-library.md` gives that sentence no citation; the link was added at
transcription. Card 5 lists the paper but no claim cites it, though its insulin-at-37 °C and
outage sentences would support one. Card YAML was not changed.

## 2026-09-23 — cold start on the free instance: bake the caches into the image

Report: on Render the Monitor took ~25 s to draw, Scenarios/Cards switches were very slow,
live data >30 s. **Warm Render was fine** (headless Chrome, 2026-09-23 16:5x UTC: Monitor
4.9 s to network idle, switch to Uri 1.3 s, Scenarios and Cards ~2 s each). The slowness is
the **cold start**: the free instance sleeps after 15 min idle, so most visits hit a fresh
process on 0.1 CPU. Reproduced with the image under `docker run --cpus=0.1 --memory=512m`
(harsher than Render, so read ratios, not seconds): right after boot Uri took 105 s,
`/replays` 84 s, `/scenarios` 59 s. The startup warm-up thread added in 830d761 ran 273 s
inside the web process (same GIL, no `nice`) while the live refresh ran 144 s + 134 s beside it.

**Done.** `make lint test` green (287 passed, 9 skipped).
- `scripts/bake_cache.py` runs in the Dockerfile after ingest/match and writes
  `CACHE_SNAPSHOT=/app/cache/snapshot.pkl` (28 entries, 18.9 MB, 1.5 s at build): Monitor's
  replay bodies, Scenarios/Cards stats, scenario summaries, the three boundary files. The app
  loads it at startup (0.3 s on 0.1 CPU) and then skips the warm-up thread; without the env
  var or the file, behaviour is unchanged. Keys are the request-time keys (`replay_version`,
  file mtimes), so a stale entry is never hit. Test: bake → clear → load → every boundary,
  replay, `/scenarios`, `/replays`, `/card-library` request adds no new cache key.
- `scenario_summary` uses a plain dict instead of `lru_cache` so the snapshot can seed it.
- Emulated after: Uri switch 105 → 2.5 s, `/replays` 84 → 15 s (6 s without live refresh).

**Not fixed — the live refresh at boot.** Live events cannot be baked; every wake re-runs
ingest + match (~2.3 s CPU locally, 1.2 + 1.0; network ~7 s) in fresh subprocesses, so the
live view is empty for the first minute or so on Render and first-page requests share the CPU
with it. The remaining lever is not waking cold: a paid instance (no sleep, 0.5 CPU) or a
keep-alive ping.

**Not yet verified on Render** — needs a push to `main`.

## 2026-09-22 — boundary payloads: revalidation and map precision

Chased a report that the "20 second delay switching tabs" was back after the welcome-screen
deploy. It was not a regression from that commit, which touched no API and no data path.
**Measured on Render**: the server-rendered pages were fine (Monitor 0.44–0.79 s, Scenarios
2.3–2.5 s, Cards 1.4–1.9 s, Sources 1.0 s). The delay is the map's boundary files —
`/reference/counties` 1.59 MB in 21.8 s and `/reference/states` 0.52 MB in 7.3 s, about
100 KB/s out of the free instance. They carry `max-age=86400`, so the cost is paid once per
browser per day and is invisible afterwards; a hard refresh to look at the new screen put it
back on the cold path. The 3–4 s on later switches is `/events` + `/action-items`, which are
never browser-cached. 830d761 fixed the server-side compute, not the download.

**Done.** `make lint test` green (286 passed, 9 skipped). Served bytes 2.11 → 1.32 MB (−37%),
about 29 s → 18 s cold on the hosted instance, and 0 bytes on revalidation.
- `_cached` now hashes each body (blake2b of the raw bytes) and sends `ETag`, with
  `Last-Modified` on the boundary files, and answers `If-None-Match` with a 304. The key
  already determines the body, so the digest cannot go stale. The gzip and identity
  representations get different tags, so a 304 is never sent for a body the client has not
  seen — there is a test for exactly that.
- `counties.display.geojson`: the browser's copy, `id` + geometry only, coordinates at 3
  decimals (~110 m) with the consecutive duplicates that rounding creates dropped. 1.59 →
  0.94 MB gzipped. Built by `build_county_boundaries.py`, which now writes both files
  (`--display-only` rederives it from the committed source without re-fetching Census).
- `states.geojson` is display-only — nothing joins against it — so it was rebuilt in place at
  3 decimals instead of 4: 0.52 → 0.38 MB.

**Decisions.**
- **`counties.geojson` itself is untouched.** `CountyIndex` ray-casts facilities against it
  with a per-feature bbox prefilter, so rounding it to ~110 m could silently move a facility
  near a county line into the wrong county, and with it that facility's panel. Two copies is
  the point: the map gets outlines, the engine keeps the geometry. A test asserts the served
  copy has no bbox or properties and the join file still does.
- Generated at build time, not per request: the transform is 1.4 s and 76 MB of heap here,
  which is roughly 19 s on the free instance's shared CPU — it would move the cost rather
  than remove it. The file is a rebuildable fixture like the others.
- `max-age` stays at 86400. A longer window would leave a deploy's boundary changes unseen,
  since the URL carries no version; the ETag is what makes the daily expiry cheap now.

**Verified on Render** (92fb20d, after the deploy): counties 1,592,451 → 942,603 B,
states 517,233 → 382,038 B, 2.11 → 1.32 MB together. `If-None-Match` returns 304 with an
empty body on both. Wall-clock for counties was 6.2 s then 1.8 / 0.7 / 0.6 s on repeat,
against 21.8 s and 25.7 s before — but the instance was plainly less contended during the
second measurement, so treat the byte counts as the result and the seconds as indicative.
Free-instance throughput moved by more than 10× between two measurements of the *same*
build, which is worth remembering before reading any single timing as a regression.

**Follow-ups.**
- Cloudflare in front of Render answers `cf-cache-status: DYNAMIC` for these — it does not
  edge-cache `application/geo+json`, so every cold browser still pulls from the origin.
- Real geometry simplification (Douglas–Peucker) would beat precision rounding by a lot at
  this zoom, but it changes the outlines and needs checking against the rendered map.
- `/events` and `/action-items` now carry an ETag too, but no `Cache-Control`; giving the
  replay responses a short one would turn the 3–4 s Monitor revisit into a 304.

**Next:** back to the implementation plan (M6 → M10).

## 2026-09-22 — welcome / about screen + guided tour

Built the welcome screen from `design_handoff_welcome/README.md` in the existing stack
(Jinja2 + `static/app.css` + vanilla JS, no new dependencies). The bundled
`Welcome Screen.dc.html` was a visual reference only and is not shipped.

**Done.** `make lint test` green (283 passed, 9 skipped).
- `templates/_about.html`: one partial, three surfaces — the modal `<dialog id="welcome">`
  rendered server-side into every page, the plain `/about` page (no-JS visitors and search),
  and the About pill in the nav. Copy is verbatim from the handoff.
- `static/welcome.js` (~250 lines): `showModal()` on a first visit, dismissal via ×, Esc,
  backdrop click, "or explore on your own" or any Try-it link, and the four-step tour.
  Dismissal writes `localStorage['mxe.welcome.seen'] = WELCOME_VERSION`; a one-time hint
  under the About button says where the screen went. `?about=1` forces it open, `?tour=1`
  starts the tour.
- The tour dims the Monitor with four panels around the step's target rather than lowering
  the app's z-index: the target stays visible and clickable, and no stacking context has to
  be rearranged. Placement is recomputed on resize and docks to the bottom on phones. ←/→
  and Esc are captured so the Monitor's own bindings for those keys stay put while it runs.
- Header: an About pill on every page, including the standalone `playback.html` (Monitor
  does not extend `base.html`, so both templates include the partial).

**Decisions.**
- `WELCOME_VERSION = "2026-09"` lives in `views.py` and is rendered into `data-version`;
  bumping it re-shows the screen to everyone once. `tour_url` is a Jinja global so the Uri
  peak-hour deep link is written once.
- Coming next carries two items beyond the handoff's four, at the user's request:
  "Implement Simulation Mode" and "Review Climate Rx Cards with Medical KG and Medical
  LLMs". The second keeps "Medical KG", which breaks this screen's no-acronyms copy rule —
  flagged and kept at the user's direction.
- The Uri Try-it link drops the handoff's `card=outage-dialysis`: with it, Monitor opened
  that card's reading view and a shrunken inset map, not the map you get by switching the
  View menu to uri_2021. `URI_URL` in `views.py` is now the single definition of that deep
  link, and `TOUR_URL` is built from it, so the peak hour is written once.
- The tour overlay sits at `z-index:1200`: Leaflet's control container is 1000 and was
  painting its zoom buttons over the coachmark.
- `@media (max-height:800px)` tightens the dialog instead of letting it scroll, so it fits a
  1366×768 laptop with the footer visible (verified in a real browser).

**Follow-ups.**
- Both Try-it link targets and the map-vs-card-detail difference were checked in a real
  browser; the dismissal hint and the localStorage round-trip were reasoned through, not
  exercised in one: headless Chrome here cannot click, and its viewport clamps at 500 px wide, so
  phone widths were checked at 500 px rather than 390 px.
- `docs/` screenshots still show the pre-About header.

**Next:** back to the implementation plan (M6 → M10).

## 2026-09-22 — hosted performance (Render free CPU)

**Measured on Render** (before): Scenarios 26–29 s every time, Cards ~8.4 s every time,
Monitor switching to Uri ~24 s (`/events?scenario=uri_2021` 15.4 MB in 15 s, action items
1.9 MB in 9 s), county outlines 5.5 MB re-gzipped at level 9 on every Monitor load. Locally
the same work is ~14× faster, which is why it felt fine locally. Causes: every request
validated thousands of stored rows into Pydantic models and re-serialized them; the
EAGLE-I attribution and caveats were repeated on each of ~13k outage events (3.8 MB of the
16 MB); GZip level 9 on megabyte bodies; nothing cached per replay although replays only
change on re-ingest/re-match.

**Done.** `make lint test` green (277 passed).
- `store.compact_events` / `compact_action_items` / `action_item_facts`: read columns (and
  the stored JSON payload) without model validation. `/events?compact=1` returns map and
  timeline fields only, with the EAGLE-I attribution once at the top level (Uri: 15.4 → 4.6 MB
  raw, 0.17 MB gzipped); Monitor uses it and fetches a selected event's full record from
  `/events/detail` on demand. Compact `/action-items` uses the fast path (a test checks it
  equals the validated path, row for row and in order).
- Replay responses are cached in-process as (raw, gzip) bodies keyed on
  `store.replay_version` — row counts, latest write times and the count per status, so
  Acknowledge / Mark completed invalidate it (tested). The Scenarios and Cards per-replay
  stats are memoised on the same fingerprint.
- Reference boundary files are gzipped once and sent with `Cache-Control: max-age=86400`;
  GZipMiddleware drops to level 5 (level 9 cost ~0.5 s per counties response locally, ~6 s
  hosted, for the same size).
- When live refresh is on (hosted/container), a startup thread warms the replay caches with
  the exact keys Monitor requests (tested), so the first visitor after a deploy doesn't wait.
- The hourly live refresh subprocess runs under `nice -n 10` so page requests get the CPU
  first while it runs.
- Local after (first / repeat): Scenarios 0.76 / 0.07 s (was 1.95), Cards 0.10 / 0.05 s
  (was 0.60), Uri events compact 0.23 / 0.01 s (was 0.70), Uri items 0.20 / 0.01 s.

**Verified on Render** (830d761, after the first live refresh finished; three rounds):
Scenarios 1.3–1.5 s (was 26–29), Cards 1.1–1.4 s (was ~8.4), Monitor on Uri — events
0.5 s + items 0.4–0.55 s (was ~15 + 9 s), live Monitor data 0.2–0.5 s events + 0.8–1.4 s
items, county/state outlines 0.14–0.23 s on repeat (was 3.5–5 s). During the first live
refresh after a deploy (~1–2 min) pages are ~2× slower; a cold start after ~15 min idle
still costs the instance wake-up.

## 2026-09-22 — Monitor (one main view), Scenarios and Cards tabs, neighbouring countries

Decided with the user in a grilling session (plan: one live-first view; details below).
`make lint test` green (274 passed); verified end-to-end in Chrome on a fresh DB with a real
live ingest.

**Done.**
- **Monitor at `/`** replaces the Dashboard and Playback tabs (playback.html + playback.js).
  Nav on every page: **Monitor · Scenarios · Sources · API**. Events tab removed from nav; the
  events table and event pages stay (rail link "all events in this window →"; event pages
  link "open in Monitor at this time →"). `/playback` and `/dashboard/facilities/{id}`
  307-redirect into Monitor with scenario/at (and `facility=`). `dashboard.html` and
  `facility.html` deleted; `/dashboard/facilities/{id}/cards` (the card block) stays.
- **URL holds the view** (`scenario, at, card, facility, event`): replaceState while
  scrubbing (throttled), pushState on selection/scenario changes, popstate restores. Live
  at now omits `at`. URL/typed times without a zone are UTC (`parseUtc`).
- **Typed time**: click the clock → datetime-local input (UTC). **Live window**: now − 14 d …
  furthest forecast/lead end, capped at now + 7 d, opens at now; dashed "now" marker and a
  Now button.
- **Outreach chip** in the banner (care-team items, acuity rank ≤ 1, still issued; class
  names from the items); click filters rail and badges. Acknowledge/Complete in the card
  block updates the prefetched item via `htmx:afterRequest`, so the count drops at once.
- **Rail ranking** matches the old board: acuity, severity × rank_score, stations first
  (anchor classes passed from the profile as `data-anchors`), name.
- **Scenarios tab (`/replays`)** — `/scenarios` is the JSON API. `data/scenarios.yaml`
  (loader `src/xevents/scenario_guide.py`): story, "what it exercises", guided moments per
  replay, plus cataloged-not-built rows from `fixtures/events/CATALOG.md`. Stats computed.
  `tests/test_golden.py::test_scenario_guide_moments_fire` runs every replay and checks each
  moment's card fires at `at`. **Narratives are Claude's draft — user review pending.**
- **Neighbouring countries**: `scripts/build_countries.py` → `fixtures/reference/countries.geojson`
  (Natural Earth 1:50m, public domain; Canada, Mexico, Cuba, Bahamas; 195 KB; raw zip in
  `raw/`), `/reference/countries`, drawn under the counties in `map.js` (optional fetch).
  Added to `make reference`, the reference README and `data/sources.yaml`.
- Docs: `user-interface.md` restructured (§4 Monitor, §5 card block, §8 Scenarios), guide
  index, README and deploy URL tables; dated notes in `medical-layer.md` and
  `events-and-playback.md`. Screenshots recaptured: monitor-live, playback-uri, card focus, cards, card-detail,
  facility-uri, smoke-2026, scenarios, sources; `dashboard-live.png` removed.

- **Cards tab** (`/card-library`, `/card-library/{id}`; `/cards` is the JSON API), between
  Scenarios and Sources. Overview: 8 tiles (acuity position from the profile, evidence tier,
  lead window, triggers in plain words, selection, "fires in" replay chips deep-linking to
  each card's peak hour, live-now count). Detail: the whole card verbatim — triggers,
  population codes and sub-panels, actions by phase, patient/caregiver text, safety line,
  escalation (null → profile default), hooks, evidence claims with tiers, sources, carbon
  (unscaled), where it fires. The safety line now comes from `engine.safety_message`, shared
  by the engine and the page; the carbon table is a `macros.html` macro used by both the card
  block and the card page. A test checks every action, sentence, sign, claim and source of
  every card appears verbatim on its page.

- **Live on the Scenarios page and as Monitor's default.** The Monitor tab is a plain `/`
  (live, now) on every page — it used to carry the current page's scenario and time. The
  Scenarios page opens with a Live card: description from `data/scenarios.yaml` (`live:`),
  numbers computed per request (`views._live_summary`: events in the −14 d…+7 d window by
  source, active now, cards and facilities now, over the window, forecasts ahead, last feed
  run, partial-coverage sources from `data/sources.yaml`).
- Heat triggers: cards 1/2/4 fire on NWS heat products (connected, live and replay); their
  second trigger, NWS HeatRisk (gridded forecast raster), has no provider yet.

**Decisions.** Tab named **Monitor** (user's choice). Facility-only selection opens focus.
Scenarios page URL `/replays`. The outreach threshold (`acuity_rank <= 1`) is the old
dashboard's rule, unchanged.

**Pending.** User review of the scenario narratives. Still-old screenshots:
`dashboard-heat-dome.png` (medical-layer.md), `playback-heat-dome*.png`
(events-and-playback.md). Push to `main` on the user's go.

## 2026-09-22 — Sources tab, `make container`, design bundle

- **Sources tab** (`/sources`, after API in both headers): one card per source the demo
  uses, grouped event / shared / medical, with what it provides, what it drives, live
  coverage (partial coverage in amber and called out at the top: EAGLE-I GA and OH only,
  AirNow monitor areas), access, cadence, limits, attribution, and the last live run per
  provider. Replays carrying a source are computed (`scenario_summary` gained `sources`);
  VA facility counts come from the DB (1,400 facilities, 184 stations, 18 VISNs, 57 states
  and territories on the demo DB). Text lives in the new `data/sources.yaml`
  (`src/xevents/sources.py` loads it, strict schema); the "Not yet connected" list is read
  from `data/hazard_sources.yaml` `backlog` rows, so the backlog is not duplicated. Map view
  of coverage deliberately deferred (text first).
- **Dockerfile now copies `data/`** — the page reads it at runtime; without this the
  container and Render would 500 on `/sources`.
- **`make container`**: rebuilds `med-extreme-events:demo` and replaces `mee` on :8000.
- **Design bundle** moved to `docs/design/2026-09-playback-redesign/`: README (with a status
  note) and screenshots are committed; the `.dc.html` prototypes and `support.js` runtime are
  kept locally and gitignored there.
- `.gitignore`: `*.db-shm`, `*.db-wal`.
- A local `demo.db` older than the `feed_runs` table 500s on live pages including `/sources`;
  `make demo` rebuilds it (as noted in the handoff entry).
- **Pending (user asked to remember):** refresh the remaining guide screenshots and UI manual
  after the redesign.

## 2026-09-22 — playback redesign (Claude Design handoff)

Implemented the handoff (now `docs/design/2026-09-playback-redesign/README.md`) inside the existing Jinja2 + htmx + vanilla-JS stack
(no build step, no new Python/JS dependencies). `make lint test` green (264 passed).

**Done.**
- **One stylesheet**, `static/app.css`: the handoff's token block, every shared component
  (chip, stat-block, rank-row, action-list, escalate block, crumbs, map legend, timeline,
  patient card), both playback layouts, phone rules (<900px) and a print stylesheet. The two
  inline `:root` blocks are gone.
- **Fonts self-hosted**: IBM Plex Sans 400/500/600 and Mono 400/500, latin woff2 from
  `@fontsource` (~100 KB) plus `OFL.txt` in `static/fonts/`. New *assets*, not dependencies;
  the stack falls back to `system-ui` / system mono.
- **Playback** (`playback.html`, `playback.js` rewritten): derived layout —
  `selectedCard || selectedFacility ? focus : browse` — driven by grid areas on `#pb-body`,
  so the Leaflet container is never reparented; `invalidateSize()` after each swap, browse
  view restored on exit. Regrouped header with 19px clock (*UTC · peak hour*), replay/live
  banner (live keeps per-feed freshness and the not-an-all-clear sentence), hazard pills,
  236px legend with the grey-dot key moved into it, HTML timeline with a fixed 168px label
  column and a playhead through every lane, focus inset (190px) with county/state label and
  **expand map ⤢**, rail bars ∝ panel, "Triggered by" with outage % and polls.
- **One card block for both surfaces.** Playback's card focus fetches
  `/dashboard/facilities/{id}/cards?card=…&embed=1&at=…` — the same `cards_partial.html` the
  facility page uses — cached by the ids of the items active at *t*. `roleContent`,
  `carbonBlock` and `roleToggle` were deleted from JS; no card text is built client-side.
- **Card block** rebuilt to the reading hierarchy: 25px title, chip row (compounding chip +
  "compounding with" three keys and a count), mono provenance, stat blocks, audience toggle,
  both phases from the card with the applicable one marked *applies now*, the other at 72%
  as *reference*, the escalation block always open, sources / carbon / patient view.
- **Patient view**: light 380px card, 16.5px sentences from the item's own `actions`, print
  one card alone (Print) or all (Ctrl+P), Copy text; `?view=pair` shows the care-team block
  beside each card. **Dashboard** event board is a rank-row list (events table kept).
  **Facility page** gained the breadcrumb.
- Colours: card palette now matches the handoff tokens (1 `#3d7fdc`, 3 `#4a9d5f`,
  6 `#e368a8`, 7 `#33b5c9`), with a test that `CARD_COLORS` equals `--card-N`; map cold
  hazard → `#33b5c9`.
- Tests rewritten where they pinned the old JS string builders or markup (playback card
  detail, carbon/two-audiences, compounding chip, EAGLE-I phase label, emPOWER stat block);
  new tests for colour parity, the embedded partial, and the pair/print view.

**Decisions / deviations from the handoff.**
- **Patient card headline = card title.** The mock's "Power outage in your area and you
  depend on dialysis" is not in card YAML (constraint 4), so it is not used. A reviewed
  plain-language headline would be a card-content addition. **Needs clinical review.**
- **Smoke hue stays `#b5894e`** (map.js's earlier fix; the token's `#8c6d3f` read as
  unshaded). Card 8's chip stays `#8c6d3f`.
- **Legend attribution keeps the full mandatory EAGLE-I string**, not the mock's shortened
  "U.S. DOE" note (v2 invariant).
- **Facility-only selection also uses the focus layout** (reading column shows every card at
  the facility); the handoff derived focus from `selectedCard` only. Event selection stays in
  browse.
- Guide screenshots `playback-uri.png` and the new `playback-card-focus.png` are current;
  `dashboard-*`, `facility-uri.png`, `playback-heat-dome*` and `playback-smoke-2026.png`
  predate the redesign.

**Next.** Refresh the remaining guide screenshots; rebuild the `mee` demo container and
deploy (push to `main` after CI).

## 2026-09-22 — session handoff: state of the system

**Where things stand.** Iteration v2 (M6–M10) is complete, reviewed and deployed. `main` is
the deployed branch; working tree clean except the untracked `docs/ui_design/` (a playback
redesign handoff, deliberately not committed — to be picked up in its own session).

- **Public demo:** <https://med-extreme-events.onrender.com> — Render blueprint
  (`render.yaml`), free plan, auto-deploys `main` only after the GitHub `ci` workflow (lint +
  262 tests) passes. First live refresh after a deploy takes ~3 min on the free CPU; the
  instance sleeps after ~15 min idle and refills live data on wake.
- **Local demo container:** `mee` on :8000 from image `med-extreme-events:demo`. It must be
  **rebuilt**, not restarted, to pick up code (`docker build -t med-extreme-events:demo . &&
  docker rm -f mee && docker run -d --name mee --restart unless-stopped -p 8000:8000
  med-extreme-events:demo`). Live data refreshes itself inside the container.
- **Replay scenarios (5):** `heat_dome_2021`, `ian_2022` (with EAGLE-I FL outages),
  `smoke_nyc_2023`, `uri_2021` (headline: legacy cold names, TX outages, cold×outage boost),
  `smoke_canada_2026` (HMS + keyless AirNow archive + heat dome). Five goldens pin them;
  regenerate with `UPDATE_GOLDEN=<scenario>|all` and review the diff.
- **Cards (8):** 1–6 from `docs/card-library.md`, 7 (cold) and 8 (smoke) plus the Card 6
  electricity-dependent DME sub-panel from `docs/card-library-additions.md`.
- **Live feeds (all keyless, refreshed at startup and hourly, `LIVE_REFRESH_MINUTES=60`):**
  NWS CAP + 14-day IEM archive, OpenFEMA, NOAA HMS smoke, AirNow public files (hourly monitors
  + reporting-area forecasts → Card 8 pre-event), EAGLE-I **Georgia and Ohio only** via public
  state mirrors (`EAGLEI_FEATURE_URL`). Every provider run is recorded (`feed_runs`) and shown
  in the live banner with the outage coverage.
- **Docs to start from:** `docs/guide/README.md` (index), `docs/guide/user-interface.md`
  (every screen: how to use it and how it is meant to work), `docs/guide/data-sources.md`,
  `docs/deploy.md`, `docs/card-reference-for-frontend.md`.

**Open items, roughly in priority order.**

1. **National EAGLE-I live coverage** needs a FEMA partner token (`EAGLEI_TOKEN`, set as a
   Render secret; no code change) or a DOE/ORNL EAGLE-I account (may need an adapter). The
   user may not be able to get access soon; GA/OH mirrors cover the demo meanwhile. The
   mirrors are unofficial and can change or stop — the banner will show a failed/stale run.
2. **Playback redesign** — handoff in `docs/ui_design/` (untracked): two layouts on one clock
   (Browse / Card focus), inside the existing Jinja2 + htmx + vanilla-JS stack, no build step.
3. **Known UI issues** (`docs/guide/user-interface.md` §12): replay supersession is computed
   once over the whole scenario (a watch can look superseded before its warning is issued);
   status buttons have no login on the public site (changes reset on redeploy); card chips on
   the playback map are colour-only.
4. **Low-priority review leftovers** (see the 2026-09-21 review entry): equal-severity CAP
   update tie-break; duplicate event keys in one match call; items with no panel bypass
   `min_panel_patients`; direction-agnostic cross-family supersede rule (latent); hard-coded
   "Don't stop your medication" prefix; secret scan skips `.py/.json/.csv`; archive events
   keep cancelled zones; each fixture rebuild adds ~13 MB Uri blobs to git history.
5. **Recorded run-through / guide screenshots** for heat dome and Ian predate v2 (the new UI
   guide has current Uri, smoke 2026 and live screenshots).
6. **Clinical review** of Cards 7/8, the Card 6 addendum, the acuity placement of cold
   (below heart failure) and smoke (below cold), and caregiver text (empty on all cards).

**Operational notes.**

- SQLite runs in WAL mode; the schema gained `events.temporality`, action-item
  `status_before_superseded` and `rank_score`, and the `feed_runs` table — rebuild any old
  local DB with `make demo`.
- `.env` has no `NWS_USER_AGENT`; the image sets a repo-URL contact string. Local
  `make ingest` in live mode needs it exported.
- Commits carry the `Co-Authored-By` trailer; pushes to `main` deploy, so keep CI green.

## 2026-09-22 — keyless AirNow live, EAGLE-I GA/OH mirrors, observed-event windows

- **Observed events have no lead window** (`engine.item_window_start`): an observed item
  starts at the observation; forecast/imminent items keep the card's lead. Consecutive
  outage readings no longer supersede each other — each is current only in its own poll
  window. Fixes the Uri replay showing the Feb 18 reading as current on Feb 16. In Ian the
  chain is now watch → warning (same family) → observed outage, with real timing; before,
  outages reached back seven days and superseded watches that had already expired. Four
  goldens regenerated (heat dome unchanged). The compounding chip names three events and
  counts the rest.
- **AirNow without a key** (`AirNowFilesProvider`): newest `HourlyAQObs_<yyyymmddhh>.dat`
  (walks back up to 4 h) for per-monitor PM2.5/ozone AQI, and `today/reportingarea.dat`
  forecast rows for today onward (category-only forecasts use the category floor, recorded
  in `metrics.aqi_basis`; county = reporting-area centre). Forecasts are temporality
  *forecast*, so Card 8 fires pre-event. First live run: Dallas–Fort Worth and Houston ozone
  forecasts at USG → Card 8 pre-event items at both stations. The key-based API remains an
  optional second path.
- **EAGLE-I for Georgia and Ohio**: `EAGLEI_FEATURE_URL` takes several layers; the image and
  `render.yaml` list the only two public mirrors with current data (GEMA, Ohio). Per-layer
  fetch, merge per county, skip layers older than 6 h, fail only when none is current; only
  the outage fields are requested (the GA layer also holds emergency-manager contacts); a
  FEMA token goes only to `gis.fema.gov`. National live coverage still needs `EAGLEI_TOKEN`.
- **Feed runs** (`feed_runs` table, `record_feed_run` / `latest_feed_runs`): every live
  provider run is recorded, including empty and skipped ones. The live banner lists them
  (events / failed / off, time, stale) and states the outage coverage ("coverage GA, OH
  (public state mirrors); 0 county readings ≥ 10 %"); live coverage joins the EAGLE-I
  caveats wherever outage numbers render. `/feeds` returns the runs.
- Verified in the rebuilt container: 6/6 providers ok, 742 live events, ~58 MB memory.
- **Outage readings end one second before the next run** (`engine.item_window_end`): poll
  events stay contiguous for the debounce chain, but at an hour boundary exactly one reading
  is current (replay as-of times fall on the hour, so two were often shown).
- **Render, verified:** 6/6 providers, 741 live events, 1,152 live items; Card 8 pre-event at
  Dallas and Houston from the ozone forecasts, during-event across the Midwest and Northeast
  from NOAA smoke. The first refresh after a deploy takes about three minutes on the free
  plan (runs show in the banner before events land).

## 2026-09-22 — live events restored (self-refreshing); playback display fixes

- **Why live events vanished:** live rows exist only in a running instance's database. The
  `mee` container was replaced twice on 2026-09-21 to pick up v2, dropping its live events,
  and Render never ran ingestion. Live ingest itself was fine (verified: 685–737 events).
- **Fix:** `src/xevents/live_refresh.py` — with `LIVE_REFRESH_MINUTES` > 0 the web app's
  lifespan starts a daemon thread that runs `scripts/ingest.py --mode live` then
  `scripts/match.py --mode live` as subprocesses, 5 s after startup and then every N minutes;
  output goes to the host log. The image defaults to 60 min with a repo-URL `NWS_USER_AGENT`;
  `render.yaml` sets both. SQLite now opens in WAL with a 10 s busy timeout so pages keep
  reading during refresh writes. EAGLE-I is skipped (with a message) when neither
  `EAGLEI_TOKEN` nor `EAGLEI_FEATURE_URL` is set, instead of failing every refresh.
  Verified in the rebuilt container: first refresh finished ~7 s after start, 737 live
  events, 58 active, 4/4 keyless providers; container at ~60 MB afterwards.
- **Display:** AirNow names carry the reading ("AQI 220 (PM2.5)"); a shared grouping rule
  (`XMap.eventGroup` / `views.event_group`) turns them into "AirNow AQI (PM2.5)" for the
  timeline rows (231 rows → 8 on `smoke_canada_2026`), the capped "triggered by" text, and
  the dashboard event summary. Maps fit the lower 48 when events also reach Alaska, Hawaii
  or the territories (HMS smoke over Alaska had shrunk the US), on playback, the dashboard
  and event pages.

## 2026-09-21 — state borders; GitHub → Render deployment

- **State borders on every map:** `scripts/build_state_boundaries.py` →
  `fixtures/reference/states.geojson` (Census 1:5m states, same scale/vintage as the counties;
  56 features, ~500 KB gzipped), served at `/reference/states`, drawn by `XMap.create` as an
  unfilled outline above the county fill and below facility markers; legend keys it.
  Verified in headless Chrome on `uri_2021` (Texas outlined against its neighbours).
- **Deployment:** `render.yaml` blueprint — Docker web service, free plan, `/health` check,
  `autoDeployTrigger: checksPass`, so Render redeploys `main` only after the GitHub `ci`
  workflow (lint + tests) passes. One-time "New → Blueprint" in the Render dashboard; see
  `docs/deploy.md` §3. Public, replay-only; status buttons are unauthenticated and reset on
  each redeploy.
- **Local container note:** the `mee` container had been restarted, not rebuilt, so it served
  the pre-v2 image (three scenarios, six cards). Rebuilt; a restart never picks up new code.

## 2026-09-21 — independent code review and fixes (five commits)

Five read-only reviewers (engine/store, providers, denominators/cards, web, repo health)
reported; every high finding was reproduced before fixing. Fixes landed in the order of
impact, one commit each; `make lint test` green throughout (242 tests).

- **High:** supersession compared item windows (which include the pre-event lead), so a
  warning that ended June 3 superseded a separate advisory starting June 8 — now an event
  that ended before the weaker one began cannot supersede it (newer events still supersede
  older overlapping-lead ones, so the hurricane-watch → observed-outage transition holds);
  three goldens regenerated where past events had wrongly superseded later ones. Live
  ingest isolates every provider failure (httpx errors are not `OSError`). Playback no longer
  crashes in empty live mode. `parse_at` converts offsets to UTC (SQLite compares text).
- **Panel semantics:** sub-panels with no reviewed denominator (Card 3 LAI, OUD) are declared
  "not sized" instead of borrowing the schizophrenia panel; multi-condition cards (7, 8)
  headline the largest single-condition panel, labelled a lower bound; class-share wording
  only where a class exists; unknown PLACES measure / missing VetPop year raise; the profile
  check rejects emPOWER or a share as a headline denominator; every component shows a caveat.
- **Store:** whole-payload change detection; progress parked by a supersession is restored
  (`status_before_superseded` column — rebuild SQLite DBs); listing order = engine order
  (severity now counts); live dedupe seeded from stored CAP rows.
- **Docs:** five scenarios / eight cards / five goldens / EAGLE-I + emPOWER everywhere;
  `make reference` rebuilds every table.
- **Remaining mediums:** partial route 422/404; live views filter in SQL (`live_only`); the
  map legend carries the EAGLE-I attribution whenever outage counties are shaded and the
  dashboard footnote keys off all active events; `network` marker gated by
  `RUN_NETWORK_TESTS`; `build_places` builds rows before writing; emPOWER build checks layer
  names and refuses empty results; OpenFEMA pages with `$skip`; missing outage denominators
  are logged; territory abbreviations; a malformed CAP feature is skipped, not fatal; playback
  tooltip escaping; goldens now pin `acuity_rank`, `compounding_events`, `exposure`,
  `rank_score` and regenerate only for `UPDATE_GOLDEN=<scenario>|all`.
- **Not addressed (low):** later-onset tie-break for equal-severity CAP updates (spec gap,
  test encodes current behaviour); duplicate event keys in one match call; items with no
  panel bypass `min_panel_patients`; direction-agnostic cross-family rule (latent);
  hard-coded "Don't stop your medication" prefix; secret scan skips `.py/.json/.csv`;
  acknowledge button after success; colour-only card chips; archive events carry the union
  of zones ever attached (cancelled counties stay "under warning"); fixture rebuilds add
  ~13 MB Uri blobs to history.

## 2026-09-21 — M10: fixtures, catalogs, dashboard polish — iteration v2 complete

- **Uri 2021 (headline):** `fixtures/events/uri_2021/` — IEM VTEC archive Feb 10–21 2021
  (EC/CW/WS/IS/BZ/WC), TX zone geometries valid 2021-02-15, and the Texas window of the
  ORNL EAGLE-I 2021 county CSV sliced into `raw/` (6.6 MB, 15-minute rows; the 1.1 GB
  yearly file stays out of the repo, `build.py --slice-from` re-slices it). 78 cold events
  (35 arrived as legacy Wind Chill products and carry `raw_nws_event`) + 12,900 hourly
  outage events ≥ 10 % across 211 counties. Golden asserts success criterion 1 exactly:
  Card 7 from normalized legacy products, Cards 3/5/6 from observed thresholds, boosted
  Card 7 items (rank 5) with the outage keys, outage items annotated with the cold event.
- **Ian upgrade:** Florida window of ORNL 2022 sliced into `raw/` (1.4 MB); 1,756 hourly
  outage events. Golden asserts criterion 2: hurricane-watch items on Cards 5/6 are
  SUPERSEDED by observed-outage items that carry during-event actions and the emPOWER line;
  one current outage item per card/facility/role.
- **Canadian smoke July 2026:** HMS shapefiles Jul 14–20 + **AirNow public file archive**
  (`files.airnowtech.org/airnow/<yyyy>/<yyyymmdd>/daily_data_v2.dat`, keyless daily site AQI —
  the historical route the plan flagged as a risk; `parse_daily_data_v2` maps it onto the
  observation-row shape) + IEM heat products Jul 13–21, filtered to 27 corridor states.
  818 events (21 HMS, 715 county-day AQI ≥ 101 in 19 states, max AQI 934; 82 heat — the
  nationwide IEM pull also carries flood products, which the builder drops).
  Golden asserts criterion 3: Card 8 from AirNow and HMS for Milwaukee/Detroit/Baltimore/DC
  stations, heat cards where the heat dome co-occurs.
- **Engine fixes the fixtures forced:** (1) consecutive polls of one county outage no longer
  pile up active items — for observed `power_outage` the newer poll supersedes the older,
  whatever its severity (requirements §1 "never duplicate"); (2) `outage_pct` is clamped
  at 100 with `outage_pct_raw` + `data_quality_flag` kept — both Uri (1,796 hours, peak
  raw 3,380 %) and Ian (59 hours) contain counties reporting more customers out than the
  modeled total, a documented EAGLE-I data-quality issue; the event page shows the flag.
- **Performance:** `scenario_summary` rescanned every event for every hour, for every
  scenario, on every page request; with Uri that took seconds per request and stalled the
  page tests for minutes. It is now an hourly difference-array sweep, cached per fixture
  file (mtime + size): 0.26 s cold for all five scenarios, ~0 warm.
- **Dashboard polish:** temporality badge (forecast/imminent/observed) on the dashboard and
  events tables, the event page and playback; outage layer — county fill deepens with
  `outage_pct` (10 % → 60 %+) on every map, legend says so; `compounding` chip
  ("acuity +1" on boosted heat/cold items) linking the co-occurring events on the facility
  page and in playback; `extreme_cold` colour and lane; the scenario switcher lists the new
  fixtures automatically (`list_scenarios`). `data/hazard_sources.yaml` moved from `docs/`
  per D7; catalog statuses updated to `integrated`.
- **Goldens:** `uri_2021.json` (714 KB), `ian_2022.json` (regenerated: 514 KB),
  `smoke_canada_2026.json` (491 KB); heat dome and NYC smoke unchanged.
- **`make demo` from empty:** load + ingest (5 scenarios, 15,648 events) + match
  (8,666 items) in ~8 s. Uri: 32,879 trigger evaluations → 2,972 items (2,824 superseded).
- **Known limit:** playback loads a scenario's whole event list; for Uri that is 12,978
  events, 15.4 MB before the gzip middleware (~0.6 s to serialize). The dashboard and events
  pages are unaffected (they query by as-of time: 394 active events at the 2021-02-16 15:00
  peak, 383 of them outages). A future iteration could serve playback a compact event shape.
- **Success criteria:** 1–3 asserted by goldens; 4 (live EAGLE-I polling) by M7's provider
  and contract test — with the token caveat; 5 (dual denominators) by M8's page test; 6
  verified above. **Not done:** the recorded run-through (screenshots in `docs/guide/`) was
  not re-taken this session.

## 2026-09-21 — M9: Cards 7 & 8, cold taxonomy, co-occurrence boost

- **Cards transcribed** from `docs/card-library-additions.md`, clinical strings verbatim:
  `cards/07-cold-cardio-respiratory.yaml` (`extreme_cold` trigger on the seven current
  NWS cold/winter products; PLACES CHD panel with heart-failure, COPD and asthma
  sub-panels; five escalations incl. hypothermia and CO; four tiered claims + the
  medication-evidence caveat) and `cards/08-smoke-copd-asthma.yaml` (AirNow `aqi_min: 101`
  and HMS `smoke_density_min: Medium` observed; PLACES asthma panel with a COPD sub-panel;
  SABA/ICS/ICS-LABA classes so the do-not-stop line attaches; three tiered claims). The
  verbatim test reads both reviewed documents. Sentences of the patient-facing paragraphs
  are split one per action, as cards 1–6 do.
- **Event taxonomy:** `EventType.EXTREME_COLD` (cold and winter-storm products as one
  family, per requirements §4 "cold, Card 7"); `SmokeDensity` enum and
  `TriggerConditions.smoke_density_min` (counts as a metric threshold); schema regenerated.
  NWS provider tracks the seven current cold products (legacy Wind Chill names normalize
  first, never listed in cards); the IEM archive maps EC/CW/WS/IS/BZ and legacy WC codes and
  backfills them live.
- **Profile:** acuity classes `cold_cardio_respiratory` and `smoke_copd_asthma` appended
  after `heart_failure` (decision: cold sits one class below heart failure so one boost step
  lifts a compounded cold item into that class; smoke below cold — neither is specified in
  the docs, both are profile data); `co_occurrence_boost: {steps: 1, pairs: [heat→
  power_outage, extreme_cold→power_outage]}`. `Denominator.share: true` now marks the three
  share-of-condition keys explicitly, so a sub-panel keyed to a population denominator (rate,
  count, PLACES) is sized as its own panel rather than as a share — Cards 7/8 need that.
- **Engine boost** (`_apply_co_occurrence_boost`, pure): after supersession, every active
  heat/cold item whose facility county has a *qualifying* outage event (one that matched a
  card in this run, i.e. cleared threshold and the two-poll debounce) overlapping the
  item's event window moves up `steps` acuity classes (floor 0) and gets
  `compounding_events` = the outage keys; outage items in that county get the primary
  event's key as annotation only. `ActionItem.compounding_events` persists in the payload;
  the store now refreshes `acuity_rank` and the annotation on re-runs.
- **Goldens:** heat dome and Ian unchanged; `tests/golden/smoke_nyc_2023.json` added
  (848 Card 8 items; the scenario used to fire nothing).
- **Tests:** `tests/test_boost.py` — profile config, cold+outage (rank −1, class label
  unchanged, only the debounce-clearing poll is stamped, symmetric annotation without a
  bump), heat+outage, no boost below threshold / single poll / non-overlapping / non-pair
  families, determinism and the rank floor, cold products tracked under current names only.
  The untiered-claim rejection test (M0) still guards the evidence discipline for the new
  cards' schema.
- **Carbon and UI follow-through:** every card needs a costed row, so `docs/carbon.yaml`
  gains Card 7 (home oxygen concentrator electricity, derived from rated draw × US grid
  intensity, low confidence) and Card 8 (salbutamol pMDI and ICS/LABA pMDI-vs-DPI from the
  Wilkinson 2019 / Janson 2020 inhaler LCAs, propellant-dominated); the methods doc table
  matches and the card-number bound in `carbon.py` is lifted. The playback palette grows to
  eight stable card colours (cold cyan, smoke brown) so 7/8 no longer wrap onto 1/2. Cards
  7/8 are in the frontend reference table; `compounding_events` is documented there.
- **Next (M10):** Uri 2021 and Ian outage fixtures (ORNL slices), Canadian smoke July 2026
  fixture, golden tests, catalogs, dashboard polish (temporality badge, outage layer,
  compounding chip, scenario switcher).

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
  claim. ~~Needs clinical reviewer confirmation.~~ *Superseded 2026-09-23 (M11): claim tiers
  and source ids now come from the AI-drafted review in `docs/card-library.md`, pending
  clinician sign-off.*
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
