# Handoff: `/playback` redesign — med-extreme-events

> **Status: implemented 2026-09-22** (see the `PROGRESS.md` entry of that date for what was
> built and where it deliberately departs from this spec). The interactive `.dc.html`
> prototypes and their `support.js` runtime are kept out of git; the screenshots below show
> them. The code is now the reference for measurements.

Target repo: `shlyakhter1/med-extreme-events` (branch `main`).
Stack in place: FastAPI + Jinja2 templates + htmx + one vanilla-JS module (`static/playback.js`) + Leaflet with the app's own boundary files. **No build step, no npm, no external assets** — keep it that way.

## Overview

The playback view replays a hazard scenario on a US map on one clock. The redesign fixes one
structural problem and one hierarchy problem:

1. The map occupies a fixed ~half of the viewport even while the user is reading a card, so
   card text, facilities and triggering events compete inside a 400px rail.
2. Clinical content is set at rail size, so reviewed actions read like metadata.

The redesign introduces **two layouts on one clock and one selection state**:

- **Browse** — big map + right rail (cards firing, facilities by acuity, events now).
- **Card focus** — entered by selecting a card. The wide column becomes a reading column for
  the card; the map is demoted to a 190px inset at the top of the rail, scoped to that card's
  footprint, with an "expand map ⤢" control that clears the selection and returns to Browse.

It also adds: a regrouped header with the clock as the dominant value, a timeline playhead,
proportional facility panel bars, and a light print-shaped patient rendering shown beside the
care-team view.

## About the design files

The files in this bundle are **design references written in HTML** — prototypes of the intended
look and behavior. They are not production code to copy. `Playback Redesign.dc.html` uses a
small streaming-component runtime (`support.js`) purely so the mock can switch states; it has
nothing to do with the target stack.

**The task is to recreate these designs inside the existing Jinja2 + htmx + vanilla-JS
environment** — same templates, same `playback.js`, same Leaflet setup — not to introduce a
framework and not to ship the HTML.

To view the references: open `Playback Redesign.dc.html` in a browser (keep `support.js`
alongside it). Switch states with the three buttons at top right: **Browse**, **Card focus**,
**Care team / patient**.

## Fidelity

**High fidelity.** Colors, type sizes, spacing, radii and copy are final and exact; implement
them as given. Two deliberate exceptions:

- The map areas are striped placeholders. The real Leaflet map goes there unchanged — only its
  container geometry changes.
- Numeric values (panels, county counts, percentages, event names in the lists) are
  illustrative of the `uri_2021` replay's shape, **not exported values**. Do not hardcode them.
  All *clinical* strings — the card title, care-team actions, escalation signs and patient
  sentences — are verbatim from `cards/06-outage-dialysis.yaml` and must keep coming from
  `/cards`, never from JavaScript.

---

## Screens / views

### 1. Shell (applies to both layouts)

`#app` is a CSS grid, `height:100vh`, `overflow:hidden`, rows `auto auto 1fr auto`:
header row, banner row, body row, timeline footer row.

**Header** — `background:#141a21`, `border-bottom:1px solid #26313d`, padding `10px 16px`,
`display:flex; align-items:center; gap:18px; flex-wrap:wrap`. Four groups then nav:

| Group | Contents |
| --- | --- |
| Brand | `med-extreme-events`, IBM Plex Mono 13px/500 |
| View | label `VIEW` (11px, `.07em`, uppercase, `#8d9aa8`) + scenario `<select>` |
| Transport | `◀` (34×32) · **▶ Play** (min-width 96, height 32, `background:#16324f`, `border:1px solid #2f5f96`, text `#9cc4ff`) · `▶` (34×32) |
| Clock | `2021-02-16 15:00` in IBM Plex Mono **19px/500**, `letter-spacing:-.01em`, tabular numerals; then `UTC · PEAK HOUR` at 11px uppercase `#8d9aa8` |
| Step | label `STEP` + `<select>` (1 h / 3 h / 6 h / 12 h / 1 day) |
| Nav | `margin-left:auto`, 13px, gap 16. Current page is `#e8eef4` + `border-bottom:2px solid #5b9dff` |

Controls: `background:#0b0f14`, `border:1px solid #26313d`, `border-radius:7px`, padding
`5px 10px`, height 32px, hover `border-color:#40536a`.
The "grey dot = facility with no card firing" sentence **moves out of the header** into the map
legend.

**Banner** — `background:#101922`, `border-bottom:1px solid #26313d`, padding `7px 16px`,
12px `#8d9aa8`. A `Replay` / `Live` pill (`#16202b`, border `#2b4a6b`, text `#9cc4ff`, radius
20px, 11px uppercase), then the scenario name, window, cards-firing count and event count, with
the counts in `#e8eef4`. Live mode keeps the existing per-feed freshness text and the
"absence of items is not an all-clear" sentence verbatim.

**Timeline footer** — `background:#141a21`, `border-top:1px solid #26313d`, padding
`10px 16px 14px`. Above the lanes: window start (left), the sentence "one lane per product ·
bar = active window · click to jump" (center), window end (right) — all 11.5px `#6f7d8c`,
bounds in mono. Lanes are `display:grid; gap:3px`; each lane is
`grid-template-columns:168px minmax(0,1fr); gap:10px`:

- label: 11.5px `#8d9aa8`, right-aligned, `white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis` — **the 168px fixed width is required** so track width is stable
  across scenarios.
- track: `height:18px`, `background:#111820`, `border-radius:4px`, `position:relative`.
- bars: `position:absolute; top:3px; height:12px; border-radius:3px`, left/width as % of the
  scenario window, filled with the hazard color; weaker occurrences at `opacity:.5–.7`.
- **Playhead**: a 2px `#ff9c82` vertical line at the clock's position, spanning **all** lanes
  (in the mock: `height:129px` from `top:-105px` in the final row), with the current time
  (`15:00Z`) as a 10px mono label below it, centered on the line.
- More than nine lanes collapse to a `+N more` row.

### 2. Browse layout

Body row: `display:grid; grid-template-columns:minmax(0,1fr) minmax(300px,380px)`.

**Map** (left) — Leaflet, unchanged, `border-right:1px solid #26313d`, `position:relative`.
Overlays:

- Top-left: active-hazard pills — `background:rgba(11,15,20,.88)`, border `#26313d`, radius 7,
  padding `5px 10px`, 12px, each with a 9×9 radius-2 swatch in the hazard color.
- Bottom-right legend — 236px, `background:rgba(17,24,31,.95)`, border `#26313d`, radius 9,
  padding `10px 11px`, 11px. Sections: `CARDS FIRING` (10px uppercase `#8d9aa8` header) with a
  9×12 chip per card + name + right-aligned facility count; hairline; facility keys; then the
  italic `#8d9aa8` note "Outage data provided by EAGLE-I, U.S. DOE. Customers are meters, not
  people." Legend rows stay clickable to isolate a card.

**Rail** (right) — `background:#141a21`, `overflow:auto`. Section headers are 11px `.08em`
uppercase `#8d9aa8`, padding `12–14px 14px 8px`; the first is sticky at `top:0` with the panel
background and a bottom hairline.

- `Cards firing now` — one button per card, full width, `background:#141a21`,
  `border-left:3px solid #26313d`, padding `11px 14px`, hover `#1a222b`. Row 1: a 10×13 chip in
  **that card's color** (card 5 `#a05cd6`, card 6 `#e368a8`, card 7 `#33b5c9` — must match the
  legend and every other screen), the title at 13.5px/600, the acuity class right-aligned in
  11px mono `#8d9aa8`. Row 2 (12px `#8d9aa8`, gap 14): `N facilities`, `largest panel N` with
  the figures in `#e8eef4` tabular mono. Row 3: `triggered by …` at 12px `#6f7d8c`.
  Rows separate with a 1px `#26313d` grid gap — no per-row borders.
- `Facilities by acuity` — hairline rows, padding `9px 14px`: name 13px; panel right-aligned
  12px mono tabular; second line location/VISN 11px `#6f7d8c` with the acuity class right-aligned
  11px `#8d9aa8`.
- `Events now · N` — hairline rows: product name 13px plus a temporality pill (10.5px uppercase,
  1px `#26313d` border, radius 20, `#8d9aa8`); second line `where` and `N counties`, 11px
  `#6f7d8c`.

### 3. Card focus layout

Entered when a card is selected. Body row becomes
`grid-template-columns:minmax(0,1fr) minmax(280px,340px)` with `align-items:start`.

**Breadcrumb** (sticky, `top:0`, `z-index:2`) — `background:#101922`, bottom hairline, padding
`9px 18px`, 12.5px: `Cards firing now` (link, clears selection) · `/` in `#4d5a69` · current
level in 600 · a 26×26 `×` button pushed right.

**Reading column** — padding `20px 24px 28px`, `max-width:820px`:

1. Title row: a 14×18 radius-3 chip in the card color, then `<h1>` at **25px/1.2, 600,
   `letter-spacing:-.01em`**, `text-wrap:balance`.
2. Chip row (gap 7, 11.5px, radius 20, padding `2px 9px`): acuity (border `#26313d`,
   `#8d9aa8`); triggering event + CAP severity (amber: bg `#2a1f0d`, border `#6b4d1c`, text
   `#f0cf6a`); temporality → phase (red-orange: bg `#2c150e`, border `#8a3a22`, text `#ff9c82`);
   compounding chip when it applies (amber, with `· acuity +1` on heat/cold cards).
   Show at most three compounding events then `and N more` (fixes the known issue where all 14
   are listed).
3. Provenance line: 11.5px IBM Plex Mono `#6f7d8c`, `line-height:1.7` — event key, window,
   card id + version, evidence tier.
4. Stat blocks: `grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px`. Each is
   `background:#141a21`, border `#26313d`, radius 10, padding `14px 15px`: 11px uppercase label,
   value in **30px mono/500 tabular** with the unit at 13px `#8d9aa8`, a 12px `#6f7d8c`
   qualifier line, then the existing `<details>` disclosure as a 12px link ("how was this number
   computed? ▾" / "ranking formula ▾"). emPOWER keeps its full label: *measured; Medicare proxy
   — not veteran-specific*.
5. Role toggle (care team / patient & caregiver) — segmented, 12.5px, radius 7; selected has
   border `#40536a` and `#e8eef4`.
6. Action groups. Heading row: 11px uppercase `#8d9aa8` + a 1px `#26313d` rule filling the
   remaining width + a right-hand status word. **The phase that applies at `t` renders at full
   strength** with a right-hand `applies now` in `#ff9c82`, items at 15px/1.5 with a dash in the
   card color; the other phase renders at `opacity:.72`, items 14px, dash `#6f7d8c`, right-hand
   label `reference`. Order: applicable phase first. Text verbatim, never truncated.
7. Escalation — always visible, never a disclosure: `background:#2c150e`, `border:1px solid
   #8a3a22`, `border-left:3px solid #e4572e`, radius 9, padding `13px 15px`; header `ESCALATE`
   in `#ff9c82`; items 14px with the response in `#ffb4a0` bold; emergencies spelled out.
8. Safety line, when the card selects on medication: same block treatment, never collapsed.
9. Footer links row (12.5px, gap 18): `sources (N) ▾`, `carbon footprint of this card's
   therapies ▾`, `open patient view ↗`. Status buttons (Acknowledge / Mark completed) keep their
   htmx behavior.

**Rail** — `position:sticky; top:0`, `background:#141a21`:

- Map inset: `height:190px`, bottom hairline, Leaflet fitted to the selected card's counties
  only. Top-left: a 11.5px label `38 counties · TX` on `rgba(11,15,20,.88)`. Bottom-right:
  `expand map ⤢` button (`#9cc4ff` on `rgba(11,15,20,.9)`, border `#2f5f96`) which clears the
  selection → Browse.
- `Firing at` / `N facilities`: hairline rows with name 13px, panel right-aligned 12px mono, a
  **4px progress bar proportional to the panel** (`background:#1f2832`, fill in the card color,
  width = panel ÷ largest panel), location 11px `#6f7d8c`. Clicking a row opens that facility
  (nested selection, breadcrumb gains a level).
- `Triggered by` / `N events`: name 13px, temporality pill, detail 11px `#6f7d8c`
  (e.g. `41% of customers out · 4 polls`).

### 4. Care-team / patient pair

Below the card focus layout: `background:#0f151c`, top hairline, padding `22px 24px 30px`.
Header: `PATIENT & CAREGIVER RENDERING` + "same action item, verbatim card text — what the
veteran receives".

The patient card is deliberately a different object: **light**, 380px, `background:#f6f4f1`,
ink `#1b2026`, radius 16, padding `24px 24px 20px`, `box-shadow:0 18px 40px rgba(0,0,0,.45)`.

- Eyebrow: `VA · CARE ALERT` 11px `.09em` uppercase `#6b6257`, timestamp right in mono.
- Headline 21px/1.25/600; facility + expiry 13px `#6b6257`.
- Patient sentences: `<ul>` no bullets, gap 11, **16.5px/1.45** — verbatim, in card order.
- Safety line: `background:#fdeee6`, border `#e6b49a`, `border-left:3px solid #c4562b`, radius
  9, 15px.
- "Call right away if you notice:" 13px/600 + a 14.5px list; emergencies end with
  **this is an emergency (911)**.
- Footer above a `#ddd6cc` hairline: 12px `#6b6257` — decision-support disclaimer + card id and
  version.
- A print stylesheet renders this card alone, black on white, one page.

Beside it, a 320px explanatory column (13px `#8d9aa8`) and `Print` / `Copy text` controls.

---

## Interactions & behavior

- **One clock.** Map, rail, breadcrumb and timeline all describe `t`. Layout is derived from
  whether a card is selected — it is not a separate mode with its own control. Never let the
  user get stranded in a layout they cannot leave: breadcrumb, `×`, `Escape` and `expand map ⤢`
  all step out one level.
- Selection nests card → facility, as today.
- Play advances one step per tick; `Space` toggles; `←`/`→` pause and step; clicking or dragging
  the timeline jumps; clicking a bar selects that event.
- Transitions: keep them minimal and under 120ms (opacity/`background-color` only). Do **not**
  animate the grid change between layouts — an instant swap reads as faster and avoids a
  Leaflet reflow mid-transition. Call `map.invalidateSize()` after the grid changes.
- Hover: rows `#1a222b`; controls `border-color:#40536a`; timeline bars get a 1px white stroke.
- Empty and stale states keep their current wording; a stale feed in live mode must still show
  the "absence of items is not an all-clear" line.
- Responsive: below 900px the body grid becomes one column — map `38vh`, then the rail content
  as the page. Card focus becomes a pushed full-screen view with the breadcrumb as a back row
  and the map inset at 140px. The timeline moves above the map as one 28px strip with lanes
  collapsed to one row per hazard color, tappable to jump; per-product lanes stay desktop-only.
  Touch targets 44px minimum.

## State

Everything already exists in `playback.js`; the redesign only adds a derived layout flag.

| State | Type | Notes |
| --- | --- | --- |
| `scenario` | string | `live` or a replay id |
| `t` | Date (UTC) | the one clock; replays open at peak hour |
| `playing`, `stepHours` | bool, number | transport |
| `selectedCard`, `selectedFacility`, `selectedEvent` | id or null | nested selection |
| *derived* `layout` | `'browse' | 'focus'` | `selectedCard ? 'focus' : 'browse'` — drives the grid |

Data continues to come from the same endpoints (`/scenarios`, `/events`, `/facilities`,
`/action-items`, `/cards`). Card text stays server-side; the whole scenario is prefetched and
filtered client-side so scrubbing stays instant.

## Design tokens

Replace the two duplicated inline `:root` blocks (in `base.html` and `playback.html`) with a
single `static/app.css`. Variable names are unchanged, so the swap is one file plus two `<link>`s.

```css
:root {
  --bg:#0b0f14;        /* page (was #0f1419) */
  --panel:#141a21;     /* rails, header, footer, cards */
  --panel-2:#1a222b;   /* hover / selected rows */
  --inset:#101922;     /* banners, sub-headers */
  --line:#26313d;      /* every hairline — one value only */
  --ink:#e8eef4;
  --ink-2:#b6c2ce;     /* secondary prose (new) */
  --muted:#8d9aa8;     /* labels only, never body copy */
  --accent:#5b9dff;
  --accent-bg:#16324f; --accent-line:#2f5f96; --accent-ink:#9cc4ff;

  --heat:#e4572e; --cold:#33b5c9; --flood:#3d7fdc;
  --smoke:#8c6d3f; --air:#a05cd6; --outage:#d9a41a; --idle:#5b6673;

  --warn-bg:#2a1f0d; --warn-line:#6b4d1c; --warn-ink:#f0cf6a;
  --alarm-bg:#2c150e; --alarm-line:#8a3a22; --alarm-ink:#ff9c82;
  --ok-ink:#7bd88f;

  --card-1:#3d7fdc; --card-2:#e4572e; --card-3:#4a9d5f; --card-4:#d9a41a;
  --card-5:#a05cd6; --card-6:#e368a8; --card-7:#33b5c9; --card-8:#8c6d3f;
}
```

`--cold` is new to CSS (it existed only in the docs and in `playback.js`). `--card-6` is raised
to `#e368a8` for contrast on the darker background. All other hazard and card hues are unchanged,
so nothing in the legend or `docs/guide/user-interface.md` §9 has to be re-explained.

**Type** — IBM Plex Sans for everything, IBM Plex Mono for clocks, ids, counts and formulas.
Self-host both in `static/fonts/` (the app must work offline; `system-ui` is an acceptable
fallback stack). Scale: 10.5 / 11 / 11.5 / 12 / 12.5 / 13 / 13.5 / 14 / 15 / 16.5 / 19 / 21 /
25 / 30 / 38. Clinical body text never below 15px; patient-facing never below 16.5px. Tabular
numerals (`font-variant-numeric:tabular-nums`) on every figure that changes with the clock.

**Spacing** — 4px base: 3 / 4 / 6 / 7 / 9 / 10 / 12 / 14 / 18 / 20 / 22 / 26 / 38.

**Radii** — 4 timeline tracks, 5 mono tags, 6 icon buttons, 7 controls and pills-with-borders,
9–10 panels and cards, 16 patient card, 20 chips.

**Shadow** — one only: `0 18px 40px rgba(0,0,0,.45)` on the patient card. No shadows in the
operator UI.

**Contrast** — `--muted` on `--bg` is ~5.3:1 (labels and 11–12px meta only). Body copy uses
`--ink` or `--ink-2`. Every color-coded thing also carries text; the one place that currently
fails is the playback card chips on the map, which the legend and hover text must keep naming.

## Components to factor out

Each of these exists today as ad-hoc markup in two or three templates plus a string builder in
`playback.js`. Naming them once removes the drift between the server-rendered pages and the
playback panel.

| Component | Notes |
| --- | --- |
| `chip` | acuity, severity, temporality, compounding. One shape, color by role, always labelled. |
| `stat-block` | label, big mono value, unit, qualifier, provenance disclosure. Panel + emPOWER. |
| `rank-row` | hairline list row: name, sub-line, right-aligned mono figure, optional bar. |
| `action-list` | phase heading with rule; dash items; applies-now vs reference emphasis. |
| `escalate-block` | bordered warning region; signs left, response bold. Never collapsed. |
| `crumbs` | sticky breadcrumb + close. Exists in playback — promote it to the facility page. |
| `map-legend` | hazard keys, card keys, facility keys, attribution. One component, two mounts. |
| `timeline` | lane label + track + bars + playhead; fixed 168px label column. |
| `patient-card` | light, print-ready rendering of one action item; own stylesheet scope. |

## Assets

None. No images, no icon font, no map tiles, no CDN. Glyphs used are plain characters:
`▶ ◀ × ▾ ⤢ ↗ —`. Fonts are self-hosted. The striped map areas in the reference file are
placeholders for the existing Leaflet map.

## Suggested order of work

1. Extract `static/app.css` with the token block and shared component rules; link it from
   `base.html` and `playback.html`; delete the duplicated inline rules. Expect no visual change
   beyond the new neutrals.
2. In `playback.js`, split the side-panel renderer into `renderBrowse()` and `renderCardFocus()`,
   and drive the `#app` grid from `selectedCard`. Move the map into the rail as a 190px inset in
   focus layout; add `expand map ⤢`; call `invalidateSize()` after the grid changes.
3. Rebuild the card block to the reading hierarchy above — in `cards_partial.html` **and** in the
   playback card view, from the same partial if possible.
4. Regroup the playback header; move the grey-dot legend sentence into the map legend.
5. Add the timeline playhead and the fixed 168px label column.
6. Replace the dashboard event board table with `rank-row` lists (keep `/dashboard/events` as a
   table — scanning columns is the point there).
7. Move `patient_view.html` onto the light `patient-card` treatment with a print stylesheet, and
   add a side-by-side care-team / patient view to the demo route.
8. Add the phone rules (single column below 900px, 44px targets, 38vh map, collapsed timeline
   strip, card focus as a pushed view).

Known issues listed in `docs/guide/user-interface.md` §12 are engine-side and out of scope here,
except the compounding-chip overflow (step 3 caps it at three plus a count).

## Files in this bundle

| File | What it is |
| --- | --- |
| `Playback Redesign.dc.html` | The hi-fi reference. Three states via the top-right buttons: Browse, Card focus, Care team / patient. |
| `Design Handoff.dc.html` | The prioritized critique (now → next per issue, with the repo files each touches), tokens, layout rules and component list. |
| `support.js` | Runtime the two reference files need in order to open in a browser. Not part of the design. |
| `screenshots/` | Captures of the reference, in case the HTML can't be opened. |

Screenshots (viewport captures at ~925px wide — the HTML reference is authoritative for
measurements, these are for orientation):

| File | Shows |
| --- | --- |
| `01-browse.png` | Browse layout: map + rail (cards firing, facilities by acuity, events now), timeline with playhead |
| `02-card-focus.png` | Card focus, top: title, chip row, provenance, stat blocks; map inset and proportional facility bars in the rail |
| `03-card-focus-actions.png` | Card focus, scrolled: pre-event actions at reference emphasis, escalation block, footer links |
| `04-care-team-patient.png` | The care-team column and the patient card side by side |
| `05-patient-card.png` | The patient card in full: verbatim sentences at 16.5px, light treatment |
