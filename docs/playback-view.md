# Playback view — replaying a scenario on the US map

*Drafted 2026-09-20 during M2/M3; implemented with M4 (`/playback`, `src/xevents/web/`). Endpoints below exist as of M4.*

> **Historical design draft.** Kept for the reasoning behind the playback view. For how the
> interface works today, see [guide/user-interface.md](guide/user-interface.md).

## Goal

Scrub through a replay scenario (or the live window) on a US map and watch events light up
counties, facilities change state, and action items appear — the demo's "show, don't tell"
surface. It is the event board and facility drill-down of §4/M5 in the implementation plan,
with time as a first-class control.

## What the user sees

- **Map**: Leaflet, CONUS + AK/HI/PR insets are optional. Layers, all toggleable:
  1. *County layer* — choropleth of counties with an active event at time **t**, colored by
     the most severe active event type (heat / hurricane-flood / smoke / air / outage).
  2. *Facility layer* — VA health facilities as markers; grey when idle, event-colored when
     any card fires for them at **t**; size ∝ estimated affected panel (M3) once available.
  3. *Event footprints* — the stored polygons (NWS alert polygons, HMS smoke) as a faint
     overlay, so a county's color is explainable.
- **Timeline**: a scrubber spanning the scenario window (heat dome 2021-06-25 → 07-08; Ian
  2022-09-23 → 10-01 for the acute phase; smoke 2023-06-06 → 06-09). Play/pause, step by
  hour or day, speed control. The current **t** drives every layer.
- **Side panel**: at **t**, the ranked event board (severity × panel) and, on clicking a
  facility, its fired cards with sized sub-panels and the clinician/patient/caregiver text.
- **Header**: scenario switcher (three replays + "live now"), feed-freshness banner in live
  mode, and a "how was this computed" popover on every number (M3 provenance).

## How it works (API-first, no SPA build step)

Everything is a plain page under `src/xevents/web/` (Jinja2 + htmx) plus one ~200-line
vanilla-JS module for the map and timeline. Data comes from the same API the dashboard uses:

| Need | Endpoint (M5) | Data already in place |
| --- | --- | --- |
| Facilities | `GET /facilities` (GeoJSON) | M1 ✔ |
| Events active at t | `GET /events?scenario=&at=<iso>` → events with `onset ≤ t ≤ expires`, county lists, polygons | M2 ✔ (store query `list_events(active_at=)`) |
| County shapes | `GET /reference/counties` → `fixtures/reference/counties.geojson` (5 MB, 1:5m); serve simplified/gzipped or as static file | M1 ✔ |
| Action items at t | `GET /facilities/{id}/action-items?at=` and `GET /action-items?scenario=&at=` | M4 |
| Scenario window | `GET /scenarios` → id, window, event count | M2 (replay provider `window()`) |

Client logic: on scrub, fetch `/events?at=t` (small: ≤ 100 events per scenario), compute
per-county max severity, recolor the county layer, and recolor facility markers from the
action-item response. Pre-fetching the whole scenario (`/events?scenario=`) makes scrubbing
instant offline; **t**-filtering then happens client-side.

## Design decisions to make in M5

- **Time resolution**: hourly steps are enough for alerts; HMS smoke is daily. Use hourly
  and snap the scrubber.
- **County choropleth size**: 5 MB GeoJSON is fine locally; for a hosted demo, pre-simplify
  to ~1 MB with a tolerance pass in the boundary builder (`--simplify`), or use TopoJSON.
- **"Active" semantics**: an event is active at t if `onset ≤ t ≤ expires`; superseded
  events (M4) are excluded; a strengthened alert therefore replaces its watch on the map.
- **Playback of live mode**: live has no timeline; show "now" plus the 7-day forecast
  horizon as a static band.
- **Keep it Mode A**: markers and panels are aggregates; nothing patient-level exists to
  plot.

## Effort

Roughly one M5 session: the endpoints are thin wrappers over existing store queries; the
map module is the main new code; the timeline is a `<input type=range>` with a timer.
