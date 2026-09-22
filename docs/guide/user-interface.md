# User interface: how to use it and how it is meant to work

*Part of the [design and user guide](README.md). As of 2026-09-22, after iteration v2
(temporality, EAGLE-I outages, emPOWER, Cards 7–8). Public demo:
<https://med-extreme-events.onrender.com>.*

This is the single reference for the web interface. Each section says what a screen shows,
how to use it, and the rule behind what you see, so a demo presenter can explain it and a
developer can tell a bug from a design decision. The layer guides go deeper on the data:
[events-and-playback.md](events-and-playback.md) for feeds and events,
[medical-layer.md](medical-layer.md) for panels, cards and action items. Front-end rendering
rules for the card content are in [card-reference-for-frontend.md](../card-reference-for-frontend.md).

## 1. What the interface is for

The system turns public hazard feeds into **action items** for VA facilities: which stations
have patients at risk from an event, roughly how many, and what the care team and the
patients should do. The interface answers three questions:

1. **Where do we act first?** The dashboard ranks facilities by acuity and size.
2. **What exactly do we do at this station?** The facility page gives the checklist, the
   patient wording and the numbers behind them.
3. **How did this unfold?** Playback replays a scenario on the map, hour by hour.

Everything runs in **Mode A**: aggregate estimates, no patient records. An item is scoped to
a station, and its panel is an estimate with its formula attached.

## 2. Pages at a glance

| Page | URL | Use it to |
| --- | --- | --- |
| Dashboard | `/` | See which facilities have open items now, ranked, with a map and the active events |
| Facility page | `/dashboard/facilities/{id}` | Read one station's cards: checklist, patient text, provenance, status buttons |
| Patient view | `/demo/patient-view?facility=&card=` | See exactly what a patient or caregiver would receive |
| Events | `/dashboard/events` | List every event in the view, active or whole window |
| Event page | `/dashboard/events/{event_key}` | One event: its counties, fields, metrics and the items it produced |
| Playback | `/playback` | Scrub a scenario through time on the map |
| API | `/docs` | The JSON API behind every page (interactive OpenAPI) |

## 3. Controls every page shares

- **Scenario** selects what you are looking at: **live (now)**, or one of the five replays
  (`heat_dome_2021`, `ian_2022`, `smoke_nyc_2023`, `uri_2021`, `smoke_canada_2026`).
- **As of** is the moment the page describes, in UTC. A replay opens at its **peak hour**,
  the hour with the most simultaneously active events. Live opens at now.
- **The banner** under the header says which mode you are in.
  - *Replay*: the scenario and the as-of time.
  - *Live*: each feed's event count and last ingest time, marked **(stale)** after six
    hours. It always adds "absence of items is not an all-clear when a feed is stale": an
    empty board with a stale feed means "we don't know", not "nothing is happening".
- **All times are UTC**, everywhere.
- The header links (Dashboard, Events, Playback, API) keep the current scenario and time.

## 4. Dashboard (`/`)

![Live dashboard](images/dashboard-live.png)

*Live mode on 2026-09-22: 58 active events and 10 stations with open items, driven mostly
by flood products firing Card 3. The banner lists the three live feeds and their last
ingest.*

**How to use it.** Read the **Event board** from the top: it is the order in which to act.
Click a facility name for its cards. The **Outreach queue** banner counts the highest-acuity
items nobody has acknowledged yet. The map shows where the events are; click a facility dot
to open it. The **Active events** table lists what is driving the items.

**How it is meant to work.**

- **Ranking.** Facilities are ordered by their most urgent item: first the acuity class
  (dialysis, then clozapine/LAI/methadone, insulin, lithium, antipsychotics in heat, heart
  failure, cold, smoke; defined in `profiles/va.yaml`), then event severity × rank score,
  then stations before clinics. The rank score is the panel size, except for power outages,
  where it is *percent of customers out × electricity-dependent Medicare beneficiaries*.
- **Outreach queue** counts items still *issued* in the two highest acuity classes.
- **Max panel** is the largest estimated panel among the station's cards, in veterans.
- **Cards are issued only at stations** (VAMCs and health care centers that own a
  catchment), so the same estimated patients are never counted twice at every clinic.
- **Map.** Counties are shaded by the most severe active event type; facilities with items
  are white-ringed circles sized by panel and coloured by the event driving their top item;
  grey dots have nothing firing. The view fits the lower 48 when events also reach Alaska,
  Hawaii or the territories.
- **Event summary** above the board groups events by product ("Flood Warning ×40"). AirNow
  readings are grouped per pollutant ("AirNow AQI (PM2.5)").
- The table shows the first 25 events by onset, with a link to the full list. When any
  EAGLE-I outage is active, the EAGLE-I attribution and caveats appear under it.

## 5. Facility page (`/dashboard/facilities/{id}`)

![Houston VAMC during Winter Storm Uri](images/facility-uri.png)

*Houston VAMC in the Uri replay at 2021-02-16 15:00Z. The outage cards (dialysis, insulin)
carry the EAGLE-I attribution, the veteran panel and the emPOWER line, and show during-event
actions. The cold card carries the compounding chip and pre-event actions.*

**How to use it.** Toggle **care team** / **patient & caregiver** to switch between the
clinician checklist and the patient wording. Expand **how was this number computed?** under
any number to see its formula, inputs, caveats and sources. Use **Acknowledge**, then **Mark
completed**, to record progress. **open patient view ↗** shows the patient-facing rendering.

**How it is meant to work.** One block per card that fires at this station at the as-of
time. When several events fire the same card, the block shows the strongest event's item.
Each block has, top to bottom:

1. **Title and tags**: the card, its acuity class, and the triggering event with its CAP
   severity.
2. **Provenance line**: event key, the item's window, card id and version, evidence tier,
   and **temporality → phase**. The temporality of the event decides which actions apply:
   *forecast* and *imminent* events show **pre-event** actions, *observed* events show
   **during-event** actions. Phase-agnostic actions always show.
3. **Outage attribution** (outage cards only): "Electric customer outage data provided by
   EAGLE-I, Department of Energy" and "customers are meters, not people".
4. **Compounding chip** (heat and cold cards only, when it applies): **compounding · acuity
   +1**, followed by the outage events it co-occurs with. It means an observed power outage
   in the same county, above a card threshold and sustained for two polls, overlaps this
   event. The item was moved up one acuity class. Outage items show the chip too, as an
   annotation without the bump.
5. **Affected panel ≈ N veterans**: the condition-based estimate. Its popover walks the
   arithmetic: veterans in the catchment × the rate from the profile, with each sub-panel
   and its caveat. A multi-condition card (Card 7) reports its largest single-condition
   panel and says it is a lower bound. Sub-panels without a reviewed denominator are listed
   as *not sized*, never filled with a borrowed number.
6. **N electricity-dependent Medicare beneficiaries in catchment** (outage cards only):
   the HHS emPOWER count, always labelled *measured; Medicare proxy — not veteran-specific*.
   It sits next to the veteran panel and never replaces it. Its popover shows the ranking
   formula.
7. **Actions**, grouped *Pre-event (3–7 days out)* / *During event* / *Actions*. The text is
   copied verbatim from the reviewed card.
8. **Safety line**, for any card that selects on medication: "Don't stop your medication —
   contact your care team." It is never collapsed.
9. **Escalation triggers**, **sources**, and the **carbon panel** (display-only estimates of
   the card's therapies, with their disclaimer; never used for triggering or ranking).
10. **Status**: `issued` → `acknowledged` → `completed`. An item replaced by a stronger
    event becomes `superseded` and disappears from the default views. If that stronger
    event goes away, the item comes back with the progress it had.

## 6. Patient view (`/demo/patient-view`)

A read-only rendering of what a patient or caregiver would receive for one card at one
facility: the verbatim patient sentences, any caregiver note, the safety line, and the
escalation signs, with emergencies spelled out as "this is an emergency (911)". The footer
says it is decision support for contacting the care team, not a diagnosis. It is a content
demo; there are no patient accounts and nothing is sent.

## 7. Events and the event page

**Events (`/dashboard/events`)** lists every event in the view. The default shows those
active at the as-of time; **Show every event in the window** lists them all. Each row has the
product, where, **severity**, a **temporality badge** (forecast / imminent / observed),
urgency, onset and expiry, and county and facility counts.

**Event page (`/dashboard/events/{key}`)** shows one event: its counties on a map (shading
by severity, or by percent out for outages), its geography notes, all metrics, the raw
payload path, and the facilities whose items it produced. An EAGLE-I outage event also shows
*customers out of county customers (percent)*, how many polls it has been sustained, a
popover with the formula and caveats, the attribution, and a **data-quality flag** when the
feed reported more customers out than the county has (the percent is capped at 100 and the
raw value kept).

## 8. Playback (`/playback`)

![Winter Storm Uri in playback](images/playback-uri.png)

*Uri at 2021-02-16 15:00Z. Texas counties are shaded by cold (cyan) and power outage
(amber, deeper where more customers are out); state borders show the storm stops at the
Texas line. Card chips sit above the stations. The timeline has one lane per product.*

**How to use it.**

| Control | Effect |
| --- | --- |
| **View** | Pick a replay, or **live (now) — last 2 weeks** |
| ▶ Play / Pause, or **Space** | Advance the clock one step per tick |
| ◀ ▶, or **← →** | Pause and step back or forward |
| **Step** | Step size: 1 h, 3 h (default), 6 h, 12 h, 1 day |
| Click or drag the timeline | Jump to that moment |
| Click an event bar or an event in the side panel | Select that event |
| Click a facility dot or a facility in the side panel | Open that facility |
| Click a card in the legend or side panel | Isolate that card on the map and open it |
| **×**, **Escape**, or the breadcrumb | Close one level of selection |

**How it is meant to work.**

- **One clock.** The map, the side panel and the timeline all describe the moment *t*.
  A replay starts at its peak hour.
- **County shading.** Each county takes the colour of its most severe active event type.
  Opacity deepens with CAP severity; power-outage counties deepen with the percent of
  customers out instead (10 % faint, 60 % and above solid).
- **State borders** are drawn above the county fill and below the facility dots, so you can
  see which states an event covers and where it stops.
- **Map fit.** The view fits the scenario's counties, preferring the lower 48 when events
  also reach Alaska, Hawaii or the territories.
- **Facilities and card chips.** Circles are sized by panel. Above each station, a fanned
  stack of chips shows the cards firing there, one colour per card, the same colour on every
  screen.
- **Timeline.** One lane per product over the scenario window, one bar per event. AirNow
  readings share a lane per pollutant. More than nine lanes collapse into "+N more".
- **Side panel**, at *t*: **Cards firing now** (with the facilities count, the largest panel
  and a short "triggered by" summary), **Events now**, and **Facilities by acuity**.
- **Selections nest**: card → facility within that card. The breadcrumb shows the path, and
  each close returns one level. With a card selected, the map answers "where is this card
  firing?", and the card view shows its reviewed text, role toggle, facilities with panels,
  and carbon panel. Card text comes from `/cards`, so no clinical wording lives in the
  JavaScript.

![Canadian smoke, July 2026](images/playback-smoke-2026.png)

*The July 2026 smoke replay. Smoke (tan) and AirNow AQI (purple) cover the Midwest and
Northeast while the heat dome (red) fires the heat cards. Eight timeline lanes; Card 8's
trigger summary reads "AirNow AQI (PM2.5), HMS smoke (Heavy), HMS smoke (Medium)".*

## 9. Visual language

| Element | Meaning |
| --- | --- |
| County colours | Heat red · extreme cold / winter storm cyan · hurricane / flood blue · wildfire smoke tan · air pollution purple · power outage amber · no event dark |
| County opacity | CAP severity (Minor faint → Extreme strong); outages by percent out |
| Light outline | State border |
| Card colours | 1 blue · 2 red · 3 green · 4 amber · 5 purple · 6 pink · 7 cyan · 8 brown |
| White-ringed circle | Facility with a card firing, sized by panel |
| Grey dot | Facility with nothing firing |
| Severity tag | CAP severity of the triggering event |
| Temporality badge | **forecast** blue · **imminent** amber · **observed** red-orange |
| Compounding chip | Co-occurring outage; "acuity +1" on heat and cold items |
| `superseded` | Replaced by a stronger or newer event; hidden by default |

Every tag carries text as well as colour. The card chips on the playback map are colour-only;
the legend and the hover text name them.

## 10. Live and replay

- **Replay** scenarios are computed ahead of time from archived sources and never change.
- **Live** events are pulled from the feeds when the app starts and then hourly: NWS alerts
  plus a two-week archive backfill, OpenFEMA declarations and NOAA smoke. EAGLE-I outages and
  AirNow air quality join when their credentials are configured. Live data is rebuilt from the
  feeds after each restart or redeploy; the first refresh lands within about a minute.
- A live board fills with the items of alerts active now. Items whose window has passed are
  expired automatically; replay items never expire.

## 11. Principles the interface keeps

1. **Clinical text is shown verbatim.** Actions, patient sentences and escalation signs are
   reviewed content from the card files; the interface never paraphrases or truncates them.
2. **Every number has its provenance** one click away: formula, inputs, caveats, sources.
3. **The safety line always shows** under medication cards.
4. **Measured proxies are labelled.** emPOWER counts are Medicare beneficiaries, not
   veterans, and say so. EAGLE-I counts are meters, not people, and carry the DOE attribution
   wherever they render, including the map legend.
5. **No external assets.** Maps are drawn from the app's own county and state boundaries; the
   interface works offline and needs no map key.
6. **No patient data.** Items are per station; panels are estimates.

## 12. Known issues

- **Replay can show a later outage measurement as current.** Items take a lead window from
  their card (days before the event), and observed outage polls inherit it. At 2021-02-16
  15:00 in the Uri replay, Houston's outage cards show the 2021-02-18 03:00 measurement and
  its severity. Observed events should have no lead window; this is an engine change.
- **Replay supersession is time-independent.** Statuses are computed once over the whole
  scenario, so before a warning is issued its watch can already appear superseded.
- **The compounding chip lists every co-occurring poll** (14 on the Houston cold card). It
  should show the first few and a count.
- **Status buttons have no login.** Anyone on the public demo can acknowledge or complete an
  item; changes reset on every redeploy.
- **Card chips are colour-only** on the playback map.
- At an exact hour boundary two consecutive outage polls can both be active; the pages show
  the stronger one.
