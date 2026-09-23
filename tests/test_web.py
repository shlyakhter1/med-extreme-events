"""Server-rendered pages: dashboard, facility drill-down, role toggle, acknowledge, patient view."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import match
from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.models import Card, Estimate
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.replay import list_scenarios, load_scenario
from xevents.providers.va_facilities import from_geojson
from xevents.store import (
    init_db,
    make_engine,
    upsert_action_items,
    upsert_events,
    upsert_facilities,
)

REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"
pytestmark = pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")
AT = "2021-06-28T00:00:00+00:00"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    eng: Engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('web') / 'web.db'}")
    init_db(eng)
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), CountyIndex.load()).facilities
    upsert_facilities(eng, facilities)
    profile = load_profile(PROFILES_DIR / "va.yaml")
    cards = load_cards(CARDS_DIR)

    def panels(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=123.0, formula="veterans × rate (test)", inputs={})

    for name in ("heat_dome_2021", "ian_2022"):
        events = load_scenario(name)
        upsert_events(eng, events)
        result = match(
            events, cards, facilities, profile, panels, now=datetime(2026, 1, 1, tzinfo=UTC)
        )
        upsert_action_items(eng, result.items)
    return TestClient(create_app(eng))


def test_monitor_is_home_and_old_urls_land_there(client: TestClient) -> None:
    """One main view: / is Monitor. Playback and facility URLs redirect into it with the same
    scenario and time, so old links and bookmarks keep working."""
    r = client.get("/", params={"scenario": "heat_dome_2021", "at": AT})
    assert r.status_code == 200
    html = r.text
    assert "<title>Monitor" in html and 'id="scenario"' in html and 'id="pb-body"' in html
    assert "VA Medical Center (VAMC)" in html, "station classes come from the profile"
    pb = client.get("/playback", params={"scenario": "ian_2022", "at": AT}, follow_redirects=False)
    assert pb.status_code == 307 and pb.headers["location"].startswith("/?")
    assert "scenario=ian_2022" in pb.headers["location"]
    fac = client.get(
        "/dashboard/facilities/vha_648",
        params={"scenario": "heat_dome_2021", "at": AT},
        follow_redirects=False,
    )
    assert fac.status_code == 307
    loc = fac.headers["location"]
    assert "facility=vha_648" in loc and "scenario=heat_dome_2021" in loc and "at=" in loc
    assert client.get("/dashboard/facilities/vha_nope").status_code == 404
    assert client.get("/", follow_redirects=False).status_code == 200


def test_events_table_defaults_to_peak_hour(client: TestClient) -> None:
    r = client.get("/dashboard/events", params={"scenario": "ian_2022"})
    assert r.status_code == 200
    assert 'value="2022-09-2' in r.text  # as-of defaulted inside the scenario window
    assert "Replay" in r.text and "ian_2022" in r.text


def test_live_pages_have_freshness_banner(client: TestClient) -> None:
    r = client.get("/dashboard/events")
    assert r.status_code == 200
    assert "Live mode" in r.text and "no live events ingested yet" in r.text
    assert "absence of items is not an all-clear" in r.text
    assert client.get("/dashboard/events", params={"scenario": "nope"}).status_code == 404
    js = client.get("/static/playback.js").text
    assert "absence of items is not an all-clear when a feed is stale." in js
    assert '"/feeds"' in js, "Monitor shows each live feed's last run"


def test_card_block_roles_and_acknowledge(client: TestClient) -> None:
    """The card block (what Monitor shows for a card or facility) carries the verbatim
    checklist, provenance, and the status workflow."""
    base = {"scenario": "heat_dome_2021", "at": AT}
    cards_url = "/dashboard/facilities/vha_648/cards"
    html = client.get(cards_url, params=base).text
    assert "Extreme Heat × Bipolar Disorder on Lithium" in html
    assert "Generate the lithium roster" in html, "clinician checklist rendered verbatim"
    assert "how was this number computed?" in html and "veterans × rate (test)" in html
    assert "Acknowledge" in html
    patient = client.get(cards_url, params={**base, "role": "patient"})
    assert patient.status_code == 200
    assert "Heat can push your lithium to a dangerous level." in patient.text
    assert "stop your medication" in patient.text  # apostrophe is HTML-escaped
    caregiver = client.get(cards_url, params={**base, "role": "caregiver"})
    assert "No caregiver content" in caregiver.text
    item_id = html.split('hx-post="/dashboard/action-items/')[1].split("/status")[0]
    ack = client.post(
        f"/dashboard/action-items/{item_id}/status", params={"status": "acknowledged"}
    )
    assert ack.status_code == 200 and "acknowledged" in ack.text
    assert "Mark completed" in client.get(cards_url, params=base).text
    assert (
        client.post(
            f"/dashboard/action-items/{item_id}/status", params={"status": "issued"}
        ).status_code
        == 409
    )
    assert client.get("/dashboard/facilities/vha_nope/cards", params=base).status_code == 404


def test_patient_view(client: TestClient) -> None:
    r = client.get(
        "/demo/patient-view",
        params={
            "facility": "vha_648",
            "card": "heat-lithium",
            "scenario": "heat_dome_2021",
            "at": AT,
        },
    )
    assert r.status_code == 200
    assert "Heat can push your lithium to a dangerous level." in r.text
    assert "Call right away if you notice" in r.text
    assert "Generate the lithium roster" not in r.text, "no clinician text in the patient view"
    assert "decision support for contacting your care team" in r.text
    # Patient and caregiver are one audience: the caregiver note sits with the patient text
    # rather than behind a separate view.
    assert "whoever is helping them" in r.text
    assert "Switch to caregiver" not in r.text
    assert (
        client.get(
            "/demo/patient-view",
            params={"facility": "vha_648", "card": "nope", "scenario": "heat_dome_2021"},
        ).status_code
        == 404
    )
    assert client.get("/demo/patient-view", params={"facility": "vha_nope"}).status_code == 404


def test_form_submitted_timestamp_is_accepted(client: TestClient) -> None:
    """A browser GET form encodes '+' as a space, so the page used to reject its own
    as-of value with 'bad timestamp'. Every accepted spelling must round-trip."""
    for value in (
        "2021-06-28T00:00:00 00:00",  # what the form actually submits
        "2021-06-28T00:00:00+00:00",
        "2021-06-28T00:00:00Z",
        "2021-06-28T00:00",  # datetime-local
        "2021-06-28",
    ):
        r = client.get("/dashboard/events", params={"scenario": "heat_dome_2021", "at": value})
        assert r.status_code == 200, f"{value!r} → {r.status_code} {r.text[:120]}"
    assert client.get("/dashboard/events", params={"at": "nonsense"}).status_code == 422
    # an offset is converted, never carried into the SQLite wall-clock comparison
    from xevents.timeparse import parse_at

    parsed = parse_at("2021-06-01T16:30:00+05:00")
    assert parsed == datetime(2021, 6, 1, 11, 30, tzinfo=UTC)
    assert parsed is not None and parsed.utcoffset() == timedelta(0)
    r_off = client.get(
        "/events", params={"scenario": "heat_dome_2021", "at": "2021-06-28T05:00:00+05:00"}
    )
    r_utc = client.get(
        "/events", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00:00Z"}
    )
    assert r_off.json()["count"] == r_utc.json()["count"], "same instant, same events"
    # the header control must emit a value the form can submit back unchanged
    html = client.get(
        "/dashboard/events", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00"}
    ).text
    assert 'type="datetime-local" name="at" value="2021-06-28T00:00"' in html
    # Monitor's URLs and typed times are UTC even without a zone suffix
    js = client.get("/static/playback.js").text
    assert "const parseUtc" in js and "`${s}Z`" in js


def test_events_pages(client: TestClient) -> None:
    base = {"scenario": "heat_dome_2021", "at": AT}
    r = client.get("/dashboard/events", params=base)
    assert r.status_code == 200
    assert "Excessive Heat Warning" in r.text
    assert "2021-06-2" in r.text, "events must show their timestamps"
    all_events = client.get("/dashboard/events", params={**base, "window": "all"})
    assert all_events.text.count("<tr>") > r.text.count("<tr>")
    key = r.text.split("/dashboard/events/")[1].split("?")[0]
    detail = client.get(f"/dashboard/events/{key}", params=base)
    assert detail.status_code == 200
    assert "Affected counties" in detail.text and "Action items produced" in detail.text
    assert client.get("/dashboard/events/nws:nope", params=base).status_code == 404


def test_events_show_location_and_timestamps(client: TestClient) -> None:
    base = {"scenario": "ian_2022", "at": "2022-09-27T16:00"}
    html = client.get("/dashboard/events", params=base).text
    assert "<th>Where</th>" in html and "<th>Onset (UTC)</th>" in html
    assert (
        'class="tag temporality forecast"' in html or 'class="tag temporality imminent"' in html
    ), "every event row carries its temporality badge"
    assert "2022-09-2" in html, "timestamps are rendered"
    assert "FL" in html, "location is rendered"


def test_monitor_offers_live_navigation_and_url_state(client: TestClient) -> None:
    """Live first, replays one menu away, and the URL holds the whole view (scenario, time,
    selection) so reload, Back and shared links reopen the same moment."""
    html = client.get("/").text
    js = client.get("/static/playback.js").text
    assert "if (!onsets.length)" in js and "no live events ingested yet" in js, (
        "live mode with no events must not compute Math.min() of nothing"
    )
    assert 'id="scenario"' in html
    assert 'value="live"' in js, "the view selector offers live"
    assert "Cards firing now" in js, "cards are surfaced in the main view"
    assert "selectCard" in js and "cardColor" in js, "cards can be selected and shown on the map"
    for fn in (
        "function readUrl",
        "async function applyUrl",
        "function writeUrl",
        "function editClock",
    ):
        assert fn in js, fn
    for key in ('q.get("card")', 'q.get("facility")', 'q.get("event")', 'q.get("at")'):
        assert key in js, key
    assert 'window.addEventListener("popstate"' in js, "Back restores the previous view"
    assert "history.pushState" in js and "history.replaceState" in js
    # live: the last two weeks plus forecasts ahead, capped at a week; a now marker and button
    assert "now - 14 * 24 * HOUR" in js and "now + 7 * 24 * HOUR" in js
    assert 'class="tl-now"' in js and 'id="now-btn"' in html
    # outreach queue as a banner chip that filters the rail
    assert "function isOutreach" in js and "state.outreachOnly" in js
    assert 'i.acuity_rank <= 1 && i.status === "issued"' in js
    # Acknowledge in the card block updates the prefetched items
    assert "htmx:afterRequest" in js
    # the rail keeps the old dashboard's ranking: acuity, severity × rank score, stations first
    assert "b.sev * b.score - a.sev * a.score" in js and "isStation" in js
    assert "all events in this window" in js


def test_playback_shows_card_content_and_map_symbols(client: TestClient) -> None:
    """Selecting a card must show the card itself, and cards need their own map symbol —
    a fanned chip stack — so they are not confused with the circular facility markers."""
    js = client.get("/static/playback.js").text
    for piece in ("renderCardDetail", "loadCardBlock", "drawBadges", "badgeHtml", "renderLegend"):
        assert piece in js, piece
    assert "Firing at" in js and "Triggered by" in js, "card focus lists where and why it fires"
    assert "[data-role]" in js, "the audience toggle in the card block switches role"
    assert "/cards" in js, "card definitions come from the card library"
    # The card block is the server partial, not a string builder in JS: no action text,
    # escalation or carbon rows are assembled here.
    assert "/dashboard/facilities/${encodeURIComponent(fid)}/cards?" in js
    assert 'embed: "1"' in js
    for builder in ("actions.care_team", "actions.patient", "def.escalation", "kg_co2e_per"):
        assert builder not in js, builder

    page = client.get("/").text
    assert 'id="map-legend"' in page, "the map needs a legend"
    assert "/static/app.css" in page and "<style>" not in page, "one shared stylesheet"
    css = client.get("/static/app.css").text
    for rule in (".card-badge .cards i", ".card-badge .cards.one i", "#map-legend"):
        assert rule in css, rule


def test_playback_script_defines_everything_it_calls(client: TestClient) -> None:
    """Structural guard. Editing this file by slicing between two anchors has twice removed
    a whole block of functions; the page then loads and silently does nothing on click."""
    js = client.get("/static/playback.js").text
    required = [
        "function init",
        "function loadScenario",
        "function setT",
        "function play",
        "function pause",
        "function togglePlay",
        "function drawTimeline",
        "function movePlayhead",
        "function render",
        "function renderSide",
        "function renderLegend",
        "function drawBadges",
        "function focusDetail",
        "function selectCard",
        "function selectEvent",
        "function selectFacility",
        "function loadCardBlock",
        "function renderBrowse",
        "function renderCardFocus",
        "function applyLayout",
        "function renderCardDetail",
        "function renderEventDetail",
        "function renderFacilityDetail",
        "function cardsAt",
        "function badgeHtml",
    ]
    for name in required:
        assert name in js, f"{name} is missing from playback.js"
    # every function the code calls by name must also be defined
    import re

    defined = set(re.findall(r"function (\w+)\(", js))
    for call in re.findall(r"(?<![.\w])(select\w+|render\w+|draw\w+|load\w+|focus\w+)\(", js):
        assert call in defined or call.startswith("loadScenario"), call


def test_playback_detail_can_be_closed(client: TestClient) -> None:
    """Opening a card must be reversible without guessing. Clicking the same row again did
    close it, but nothing on screen said so, and there was no way back one level."""
    js = client.get("/static/playback.js").text
    for fn in (
        "detailHeader",
        "selectionCrumbs",
        "closeTop",
        "goToCrumb",
        "clearSelection",
        "wireDetailChrome",
    ):
        assert f"function {fn}" in js, fn
    assert 'data-close="1"' in js, "an explicit close control"
    assert "data-crumb=" in js, "a breadcrumb back to the level above"
    assert 'e.code === "Escape" && closeTop()' in js, "Escape closes one level"
    assert "Close (Esc)" in js, "the shortcut is discoverable from the control"
    # closing the deepest level first, not everything at once
    close_fn = js[js.index("function closeTop") : js.index("function goToCrumb")]
    assert close_fn.index("selectedFacility") < close_fn.index("selectedCard")
    # nothing selected leaves an empty panel rather than a stale one
    assert 'else $("detail").innerHTML = "";' in js
    # the layout is derived from the selection, and every way out leads back to browse
    assert 'state.selectedCard || state.selectedFacility ? "focus" : "browse"' in js
    assert '$("expand-map").addEventListener("click", () => clearSelection())' in js
    assert "invalidateSize" in js, "Leaflet must be told when its container changes size"


def test_playback_switching_views_does_not_leak_paint(client: TestClient) -> None:
    """The paint maps record what the map layers show, and render() clears whatever the new
    view does not repaint. Emptying them on a view switch left the live view's flood counties
    and facilities painted inside the heat-dome replay."""
    js = client.get("/static/playback.js").text
    load = js[js.index("async function loadScenario") :]
    load = load[: load.index("\n  }\n")]
    assert "lastCountyPaint = new Map()" not in load
    assert "lastFacilityPaint = new Map()" not in load

    css = client.get("/static/app.css").text
    for rule in (".crumbs", ".crumbs .closebtn", ".crumbs .crumb.on"):
        assert rule in css, rule


def test_map_legend_explains_the_colours(client: TestClient) -> None:
    """Counties are shaded by event type and facilities are dots; both need a key, and a
    shaded county must never be mistakable for an unshaded one."""
    shared = client.get("/static/map.js").text
    assert "legendHtml" in shared and "EVENT_COLORS" in shared
    for label in (
        "heat",
        "extreme cold / winter storm",
        "hurricane / flood",
        "wildfire smoke",
        "air pollution",
        "power outage",
    ):
        assert f'label: "{label}"' in shared, label
    assert "outageOpacity" in shared and "shades by % of customers out" in shared, (
        "the outage layer keys the county fill off percent out and the legend says so"
    )
    assert "no active event" in shared, "the base colour needs a key too"
    assert "Shading deepens with severity" in shared
    assert "#8c6d3f" not in shared, "the old smoke brown read as unshaded at low opacity"
    assert "fillOpacity = (severityRank) => 0.34" in shared, "minor alerts must stay visible"

    page = client.get("/").text
    assert 'id="map-legend"' in page
    js = client.get("/static/playback.js").text
    assert "XMap.legendHtml" in js and "no card firing" in js


def test_card_definitions_available_for_the_playback_panel(client: TestClient) -> None:
    cards = client.get("/cards").json()
    assert len(cards) == 8
    by_id = {c["id"]: c for c in cards}
    lithium = by_id["heat-lithium"]
    assert lithium["actions"]["patient"][0]["text"].startswith("Heat can push your lithium")
    assert lithium["sources"] and lithium["evidence_tier"]
    assert lithium["window_days"] == {"min": 3, "max": 7}
    assert {c["number"] for c in cards} == set(range(1, 9)), "stable colours key off card number"
    js = client.get("/static/playback.js").text
    palette = js.split("const CARD_COLORS = [")[1].split("]")[0]
    assert palette.count("#") == 8, "one stable colour per card number"


def test_carbon_panel_in_the_card_block(client: TestClient) -> None:
    base = {"scenario": "heat_dome_2021", "at": AT}
    html = client.get("/dashboard/facilities/vha_648/cards", params=base).text
    assert "carbon footprint of this card's therapies" in html
    assert "Lithium carbonate" in html and "900 mg/day PO" in html
    assert "never for clinical decisions" in html, "the disclaimer travels with the numbers"
    assert "must not be added together" in html, "alternatives are scenarios, not a sum"
    assert "Panel t CO₂e/yr" in html

    doc = client.get("/carbon").json()
    assert len(doc["entries"]) >= 12
    assert set(doc["by_card"]) == {str(n) for n in range(1, 9)}
    assert doc["by_card"]["6"][0]["citations"], "API rows carry their citations"
    assert "ui_disclaimer" in doc


def test_playback_card_block_carbon_and_two_audiences(client: TestClient) -> None:
    """The playback card focus fetches the same partial as the facility page, filtered to one
    card; it carries the carbon table and both audiences, and the phase that applies now."""
    base = {"scenario": "heat_dome_2021", "at": AT, "card": "heat-lithium", "embed": "1"}
    html = client.get("/dashboard/facilities/vha_648/cards", params=base).text
    assert "Extreme Heat × Bipolar Disorder on Lithium" in html
    assert "must not be added together" in html and "never for clinical decisions" in html
    assert "patient &amp; caregiver" in html, "patient and caregiver are one audience"
    assert 'data-role="patient"' in html and "hx-get" not in html.split("cb-foot")[0], (
        "embedded, the audience toggle is driven by playback.js, not htmx"
    )
    assert "applies now" in html and "Escalate" in html, "escalation is never collapsed"
    patient = client.get(
        "/dashboard/facilities/vha_648/cards", params={**base, "role": "patient"}
    ).text
    assert "patient-card" in patient and "Heat can push your lithium" in patient
    assert "Generate the lithium roster" not in patient
    js = client.get("/static/playback.js").text
    # the detail panel must sit above the long lists or a selection is never seen
    detail = js.index('`<div id="detail"></div>`')
    cards_heading = js.index("Cards firing now")
    facilities_heading = js.index("Facilities by acuity")
    assert detail < cards_heading < facilities_heading


def test_card_colours_match_the_stylesheet(client: TestClient) -> None:
    """Map chips (playback.js) and server-rendered chips (app.css) must agree per card."""
    js = client.get("/static/playback.js").text
    css = client.get("/static/app.css").text
    palette = js.split("const CARD_COLORS = [")[1].split("]")[0].replace('"', "").split(",")
    for n, colour in enumerate(palette, start=1):
        assert f"--card-{n}:{colour.strip()}" in css, n


def test_patient_view_pair_and_print(client: TestClient) -> None:
    params = {"facility": "vha_648", "scenario": "heat_dome_2021", "at": AT}
    card = client.get("/demo/patient-view", params=params).text
    assert "patient-card" in card and "data-print-card" in card
    pair = client.get("/demo/patient-view", params={**params, "view": "pair"}).text
    assert "Generate the lithium roster" in pair, "care-team block beside the patient card"
    assert "Heat can push your lithium" in pair
    css = client.get("/static/app.css").text
    assert "@media print" in css and "body.print-one" in css


def test_feeds_and_scenario_peak(client: TestClient) -> None:
    feeds = client.get("/feeds").json()
    assert feeds["feeds"] == [] and feeds["stale_after_hours"] == 6.0
    scen = client.get("/scenarios").json()
    heat = next(s for s in scen if s["id"] == "heat_dome_2021")
    assert heat["window_start"] <= heat["peak_at"] <= heat["window_end"]


def test_partial_validates_role_and_facility(client: TestClient) -> None:
    """The htmx partial used to 500 on an unknown role and 200 on an unknown facility."""
    base = {"scenario": "heat_dome_2021", "at": AT}
    assert (
        client.get(
            "/dashboard/facilities/vha_648/cards", params={**base, "role": "bogus"}
        ).status_code
        == 422
    )
    assert client.get("/dashboard/facilities/vha_nope/cards", params=base).status_code == 404
    assert (
        client.get(
            "/dashboard/facilities/vha_648/cards", params={**base, "role": "patient"}
        ).status_code
        == 200
    )


def test_live_pages_do_not_load_replay_rows(client: TestClient) -> None:
    """Live views filter in SQL: no replay fixture rows are deserialized and discarded."""
    from xevents.store import list_action_items, list_events

    eng = client.app.state.engine  # type: ignore[attr-defined]
    assert list_events(eng, live_only=True) == [] and list_action_items(eng, live_only=True) == []
    assert list_events(eng, scenario="heat_dome_2021"), "scenario filtering is unaffected"
    live = client.get("/dashboard/events", params={"scenario": "live", "window": "all"}).text
    assert "Excessive Heat Warning" not in live, "replay rows must not leak into live pages"
    assert client.get("/events").json()["count"] == 0
    assert client.get("/action-items", params={"compact": "1"}).json()["count"] == 0


def test_map_legend_carries_eaglei_attribution(client: TestClient) -> None:
    js = client.get("/static/map.js").text
    assert "Electric customer outage data provided by EAGLE-I, Department of Energy." in js
    assert 'power_outage ? `<div class="note">${EAGLEI_ATTRIBUTION}' in js, (
        "the attribution renders in the legend whenever outage counties are shaded"
    )
    pb = client.get("/static/playback.js").text
    assert 'titles.map(esc).join("<br>")' in pb, "tooltip line breaks must not be escaped"


def test_maps_draw_state_borders(client: TestClient) -> None:
    """Every map overlays state outlines, so a single-state event (Uri, Texas) shows where
    the state ends; the outlines are drawn above the county fill and keyed in the legend."""
    r = client.get("/reference/states")
    assert r.status_code == 200
    doc = r.json()
    states = {f["properties"]["state"] for f in doc["features"]}
    assert len(doc["features"]) == 56 and {"TX", "FL", "PR", "DC", "AK", "HI"} <= states
    assert all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in doc["features"])
    js = client.get("/static/map.js").text
    assert 'fetch("/reference/states")' in js and "stateLayer" in js
    assert "ctx.stateLayer.bringToFront()" in js, "borders stay above repainted counties"
    assert "state border" in js, "the legend keys the outline"
    assert "fill: false" in js, "outlines never hide an event colour"


def test_airnow_readings_group_by_pollutant(client: TestClient) -> None:
    """AirNow names carry the reading; summaries and timelines group them per pollutant, and
    maps fit the lower 48 when events also reach Alaska/Hawaii/territories."""
    from xevents.web.views import event_group

    assert event_group("AQI 220 (PM2.5)") == "AirNow AQI (PM2.5)"
    assert event_group("AQI 101 (OZONE)") == "AirNow AQI (OZONE)"
    assert event_group("HMS smoke (Heavy)") == "HMS smoke (Heavy)"
    js = client.get("/static/map.js").text
    assert "const eventGroup" in js and "function summarizeNames" in js
    assert "function fitCounties" in js and 'NON_CONUS_STATE_FIPS = new Set(["02", "15"' in js
    pb = client.get("/static/playback.js").text
    assert "XMap.eventGroup(e.event_name)" in pb, "timeline rows group AirNow readings"
    assert "XMap.summarizeNames(c.events)" in pb, "card trigger text is capped"
    assert "XMap.fitCounties(ctx, fips" in pb


def test_live_banner_shows_provider_runs_and_outage_coverage(tmp_path: Path) -> None:
    """Every provider run is visible, including one that produced nothing, and the EAGLE-I
    coverage (which states) is stated wherever outage caveats appear."""
    from xevents.store import record_feed_run

    eng = make_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    init_db(eng)
    record_feed_run(eng, "hms", "hms", "ok", 6)
    record_feed_run(
        eng,
        "eagle_i",
        "eagle_i",
        "ok",
        0,
        "coverage GA, OH (public state mirrors); 0 county readings ≥ 10% of customers out",
    )
    record_feed_run(eng, "airnow (files)", "airnow", "failed", 0, "HTTP 502")
    c = TestClient(create_app(eng))
    html = c.get("/dashboard/events").text
    assert "hms: 6 events" in html and "eagle_i: 0 events" in html
    assert "airnow (files): <b>failed</b>" in html
    assert "Power outages (EAGLE-I): coverage GA, OH (public state mirrors)" in html
    assert 'class="banner stale"' in html, "a failed provider makes the banner amber"
    runs = c.get("/feeds").json()["runs"]
    assert {r["provider"] for r in runs} == {"hms", "eagle_i", "airnow (files)"}
    from xevents.web.views import event_group

    assert event_group("AQI forecast Unhealthy for Sensitive Groups (OZONE)") == (
        "AirNow AQI forecast (OZONE)"
    )


def test_sources_page_lists_every_source_and_live_limits(tmp_path: Path) -> None:
    """The Sources tab shows every registered source, states partial live coverage plainly
    (EAGLE-I: Georgia and Ohio only), joins each live feed's last run, and lists the replays
    that carry a source from the fixtures rather than from hand-written text."""
    from xevents.sources import load_backlog, load_registry
    from xevents.store import record_feed_run

    eng = make_engine(f"sqlite:///{tmp_path / 'src.db'}")
    init_db(eng)
    record_feed_run(eng, "hms", "hms", "ok", 6)
    record_feed_run(eng, "eagle_i", "eagle_i", "ok", 0, "coverage GA, OH (public state mirrors)")
    record_feed_run(eng, "airnow (files)", "airnow", "failed", 0, "HTTP 502")
    c = TestClient(create_app(eng))
    r = c.get("/sources")
    assert r.status_code == 200
    html = r.text
    registry = load_registry()
    for s in registry.sources:
        assert f'id="{s.id}"' in html, s.id
    assert {"va_facilities", "eagle_i", "nws", "airnow"} <= {s.id for s in registry.sources}
    assert "Georgia and Ohio only" in html, "the live EAGLE-I limit is stated"
    assert "live coverage is partial" in html
    assert "6 live events" in html and "last run failed" in html and "HTTP 502" in html
    assert "not an all-clear" in html, "a failed feed carries the all-clear caveat"
    assert "Electric customer outage data provided by EAGLE-I, Department of Energy." in html
    assert "Medicare proxy" in html, "emPOWER is labelled a proxy"
    assert "/?scenario=uri_2021" in html, "replays carrying EAGLE-I are computed"
    assert "facilities" in html and "stations" in html
    backlog = load_backlog()
    assert backlog and all(b.id in html for b in backlog), "backlog comes from hazard_sources"
    assert 'href="/sources' in c.get("/dashboard/events").text, "the tab is in the shared header"
    assert 'href="/sources"' in c.get("/").text
    # every live provider name in the registry is one that ingest actually records
    ingest = (Path(__file__).resolve().parents[1] / "scripts" / "ingest.py").read_text()
    for s in registry.sources:
        for name in s.live.runs:
            stem = name.split(" (")[0]
            assert f'"{stem}' in ingest or f"'{stem}" in ingest, name


def test_nav_is_monitor_scenarios_cards_sources_api(client: TestClient) -> None:
    """One main view plus reference tabs; the Dashboard, Events and Playback tabs are gone."""
    import re

    for path in ("/", "/sources", "/replays", "/card-library", "/dashboard/events"):
        html = client.get(path).text
        nav = html.split("<nav", 1)[1].split("</nav>", 1)[0]
        labels = re.findall(
            r">(Monitor|Scenarios|Cards|Sources|API|Dashboard|Events|Playback)<", nav
        )
        assert labels == ["Monitor", "Scenarios", "Cards", "Sources", "API"], (path, labels)
        if path != "/":
            assert '<a href="/" title="live, now">Monitor</a>' in nav, (
                "the tab always opens live now"
            )


def test_scenarios_page(client: TestClient) -> None:
    """Every built replay is described, with computed stats and deep-linked guided moments."""
    from xevents.providers.replay import list_scenarios
    from xevents.scenario_guide import load_guide

    r = client.get("/replays")
    assert r.status_code == 200
    html = r.text
    for sid in list_scenarios():
        assert f'id="{sid}"' in html, sid
    guide = load_guide()
    moment = guide.replays[0].moments[0]
    at = moment.at.strftime("%Y-%m-%dT%H:%MZ")
    link = f"/?scenario={guide.replays[0].id}&at={at}&card={moment.card}"
    assert link in html, "moments deep-link into Monitor at that time and card"
    assert "Cataloged, not built" in html and "Hurricane Ida" in html
    assert "cards fired" in html and "facilities" in html
    assert "Live mode" not in html, "the live banner is not shown on a reference page"
    # the live scenario comes first; with no live rows it says so rather than showing zeros
    assert html.index('id="live"') < html.index(f'id="{list_scenarios()[0]}"')
    assert "open in Monitor now" in html and "No live events ingested yet" in html
    assert "Georgia and Ohio only" in html, "partial live coverage is stated from the registry"


def test_neighbouring_countries_backdrop(client: TestClient) -> None:
    r = client.get("/reference/countries")
    assert r.status_code == 200
    doc = r.json()
    assert {f["id"] for f in doc["features"]} >= {"CAN", "MEX"}
    assert (
        "Natural Earth" in doc["provenance"]["license"]
        or "naturalearth" in doc["provenance"]["source"]
    )
    js = client.get("/static/map.js").text
    assert 'fetch("/reference/countries")' in js and "COUNTRY_STYLE" in js
    # drawn before (under) the county layer, and optional: a failed fetch never blocks the map
    create = js[js.index("async function create") :]
    assert create.index("countryGeo") < create.index("const layer = L.geoJSON(geo")
    assert ".catch(() => null)" in js


def test_card_library_overview(client: TestClient) -> None:
    """The Cards tab lists all eight cards with triggers, evidence tier and where they fire."""
    from markupsafe import escape

    r = client.get("/card-library")
    assert r.status_code == 200
    html = r.text
    cards = client.get("/cards").json()
    assert len(cards) == 8
    for c in cards:
        assert f'href="/card-library/{c["id"]}"' in html, c["id"]
        assert str(escape(c["title"])) in html, c["id"]
    assert "Excessive Heat Warning" in html, "NWS trigger products are listed"
    assert "≥ 10 % of customers out" in html and "sustained 2 polls" in html
    # the web fixture matches heat_dome_2021 and ian_2022: their chips deep-link into Monitor
    assert "/?scenario=heat_dome_2021&at=" in html and "&card=heat-lithium" in html
    assert "/?scenario=ian_2022&at=" in html and "&card=outage-dialysis" in html
    assert "Live mode" not in html


def test_card_detail_is_verbatim_and_complete(client: TestClient) -> None:
    """A card's page shows its YAML in full: every action and patient sentence verbatim,
    escalation with the templated default, the safety line, every claim and source."""
    from markupsafe import escape

    from xevents.cards import load_cards
    from xevents.engine import safety_message
    from xevents.profiles import PROFILES_DIR, load_profile
    from xevents.web.views import tel_links

    profile = load_profile(PROFILES_DIR / "va.yaml")
    for card in load_cards():
        html = client.get(f"/card-library/{card.id}").text
        for a in card.actions.care_team:
            assert str(escape(a.text)) in html, (card.id, a.text[:40])
        for a in [
            *card.actions.patient,
            *card.actions.caregiver,
        ]:  # phone numbers become tel: links
            assert str(tel_links(a.text)) in html, (card.id, a.text[:40])
        for e in card.escalation:
            assert str(escape(e.signs)) in html, (card.id, e.signs[:40])
            assert str(escape(e.response or profile.escalation_default)) in html
        for cl in card.evidence.claims:
            assert str(escape(cl.text)) in html, (card.id, cl.text[:40])
        for src in card.sources:
            assert f'id="src-{src.id}"' in html and str(escape(src.citation)) in html
        safety = safety_message(card, profile)
        assert (safety is None) or str(escape(safety)) in html, card.id
    lithium = client.get("/card-library/heat-lithium").text
    assert "Generate the lithium roster" in lithium
    assert "Heat can push your lithium to a dangerous level." in lithium
    assert "Lithium carbonate" in lithium and "must not be added together" in lithium
    assert "Panel t CO₂e/yr" not in lithium, "no panel to scale to on the card page"
    assert client.get("/card-library/nope").status_code == 404


def test_compact_payloads_and_replay_cache(client: TestClient) -> None:
    """Hosted on a small CPU, Monitor was slow because every replay request re-validated and
    re-serialized thousands of rows and repeated the EAGLE-I text on every event. The fast
    paths must return the same data, and the cache must not hide a status change."""
    from xevents.api import compact_item
    from xevents.store import compact_action_items, list_action_items

    eng = client.app.state.engine  # type: ignore[attr-defined]
    # compact events: much smaller, keep what the map and timeline read
    full = client.get("/events", params={"scenario": "ian_2022"})
    compact = client.get("/events", params={"scenario": "ian_2022", "compact": "1"})
    assert compact.status_code == 200 and len(compact.content) < len(full.content) / 2
    doc = compact.json()
    assert doc["count"] == full.json()["count"]
    ev = doc["events"][0]
    for k in (
        "event_key",
        "event_name",
        "event_type",
        "severity",
        "temporality",
        "onset",
        "expires",
    ):
        assert k in ev, k
    assert "county_fips" in ev["geography"] and "raw_ref" not in ev and "attribution" not in ev
    outage = [e for e in doc["events"] if e["source"] == "eagle_i"]
    if outage:
        assert "outage_pct" in outage[0]["metrics"]
        assert doc["eaglei"]["attribution"].startswith("Electric customer outage data provided")
    # compact action items: the column fast path equals the validated path, in the same order
    fast = compact_action_items(eng, scenario="ian_2022", include_superseded=True)
    slow = [
        compact_item(i)
        for i in list_action_items(eng, scenario="ian_2022", include_superseded=True)
    ]
    assert fast == slow
    api = client.get("/action-items", params={"scenario": "ian_2022", "include_superseded": "true"})
    assert api.json()["items"] == fast
    # the replay cache keys on the rows' fingerprint: acknowledging an item shows up at once
    params = {"scenario": "heat_dome_2021", "role": "care_team"}
    before = {
        i["id"]: i["status"] for i in client.get("/action-items", params=params).json()["items"]
    }
    target = next(k for k, v in before.items() if v == "issued")
    assert (
        client.post(
            f"/dashboard/action-items/{target}/status", params={"status": "acknowledged"}
        ).status_code
        == 200
    )
    after = {
        i["id"]: i["status"] for i in client.get("/action-items", params=params).json()["items"]
    }
    assert after[target] == "acknowledged"
    # boundary files: gzipped once, cacheable by the browser for a day
    geo = client.get("/reference/counties", headers={"Accept-Encoding": "gzip"})
    assert geo.status_code == 200 and "max-age=86400" in geo.headers["cache-control"]
    assert geo.headers.get("content-encoding") == "gzip"
    assert geo.json()["type"] == "FeatureCollection"
    # Monitor asks for the compact form and fetches a selected event's detail on demand
    js = client.get("/static/playback.js").text
    assert "compact=1" in js and "/events/detail?key=" in js


def test_cache_warm_up_fills_the_entries_monitor_reads(client: TestClient) -> None:
    """The startup warm-up must build the same cache keys Monitor's requests produce, or the
    first visitor after a deploy still waits."""
    import xevents.api as api

    eng = client.app.state.engine  # type: ignore[attr-defined]
    api._BODY_CACHE.clear()
    api._warm(eng)
    warmed = set(api._BODY_CACHE)
    assert any(k[0] == "events" for k in warmed) and any(k[0] == "items" for k in warmed)
    client.get("/events", params={"scenario": "heat_dome_2021", "compact": "1"})
    client.get("/action-items", params={"scenario": "heat_dome_2021", "include_superseded": "true"})
    assert set(api._BODY_CACHE) == warmed, "Monitor's requests hit the warmed entries"
    js = client.get("/static/playback.js").text
    assert "getJSON(`/events?${q}compact=1`)" in js
    assert "getJSON(`/action-items?${q}include_superseded=true`)" in js


def test_cache_snapshot_round_trip_serves_every_first_request(
    client: TestClient, tmp_path: Path
) -> None:
    """The image bakes its caches (scripts/bake_cache.py) and a new instance loads them. After
    a load, the map's boundary files, Monitor's replay requests and the Scenarios/Cards pages
    must all be hits: a new key would mean an instance computing it on the free CPU again."""
    import xevents.api as api
    from xevents.web import views

    eng = client.app.state.engine  # type: ignore[attr-defined]
    snap = tmp_path / "snapshot.pkl"
    assert api.bake_snapshot(eng, snap) > 0
    baked = (set(api._BODY_CACHE), set(views._STATS_CACHE), set(api._SUMMARY_CACHE))
    for cache in (api._BODY_CACHE, views._STATS_CACHE, api._SUMMARY_CACHE):
        cache.clear()
    assert api.load_snapshot(snap)
    assert (set(api._BODY_CACHE), set(views._STATS_CACHE), set(api._SUMMARY_CACHE)) == baked

    for path in ("/reference/counties", "/reference/states", "/reference/countries"):
        assert client.get(path).status_code == 200, path
    for name in list_scenarios():
        client.get("/events", params={"scenario": name, "compact": "1"})
        client.get("/action-items", params={"scenario": name, "include_superseded": "true"})
    for path in ("/scenarios", "/replays", "/card-library"):
        assert client.get(path).status_code == 200, path
    after = (set(api._BODY_CACHE), set(views._STATS_CACHE), set(api._SUMMARY_CACHE))
    assert after == baked, "every first request was served from the snapshot"
    assert not api.load_snapshot(tmp_path / "missing.pkl")


def test_welcome_is_reachable_from_every_page(client: TestClient) -> None:
    """The one screen that says what this is. It opens itself on a first visit, the About pill
    reopens it forever after, and ?about=1 forces it open in a link someone was sent."""
    for path in ("/", "/replays", "/card-library", "/sources", "/dashboard/events"):
        html = client.get(path).text
        assert 'id="about-btn"' in html, path
        assert '<dialog id="welcome"' in html, path
        assert 'data-version="2026-09"' in html, path
        assert "/static/welcome.js" in html, path


def test_about_page_renders_the_same_panel_without_the_dialog(client: TestClient) -> None:
    """/about is the no-JS and search surface. It must not also render the dialog, or the page
    would carry two elements with the same ids."""
    html = client.get("/about").text
    assert '<dialog id="welcome"' not in html
    assert 'id="about-title"' in html
    assert html.count('class="about-panel') == 1
    assert "Medical alerts for extreme weather" in html
    # No dialog means no welcome.js: the pill must not be a button that does nothing.
    assert "/static/welcome.js" not in html
    assert 'id="about-btn"' not in html
    assert '<span class="about-pill on" aria-current="page">' in html


def test_welcome_copy_is_the_reviewed_text(client: TestClient) -> None:
    """The welcome copy is reviewed content, written for someone who has never seen the app:
    no acronyms, and every claim about what works is one of the three modes."""
    html = client.get("/about").text
    for line in (
        "Medical alerts for extreme weather",
        "someone on dialysis can't miss treatment when the power goes out",
        "it estimates how many at-risk patients each nearby hospital serves",
        "Replay Winter Storm Uri, Texas 2021",
        "See what a patient receives",
        "Browse the eight alert cards",
        "Replays five past events, including Hurricane Ian and the Pacific Northwest heat dome",
        "Estimates how many alert cards a given population can expect",
        "Implement Simulation Mode",
        "Review Climate Rx Cards with Medical KG and Medical LLMs",
        "Not for clinical use.",
        "Feedback on usefulness, and collaborators on data or clinical content, are welcome.",
    ):
        assert line in html, line
    for acronym in ("VISN", "ESRD", "EAGLE-I", "emPOWER"):
        assert acronym not in html, acronym
    assert html.count("<li>") >= 6, "six Coming next items"


def test_welcome_try_it_buttons_are_real_links(client: TestClient) -> None:
    """Each Try-it is a link to a view that exists, not a stub: Uri at its peak hour, the
    patient rendering, and the card library. The Uri link carries no card= — it opens the map
    the View menu would give you, not one card's detail view."""
    import re

    html = client.get("/about").text
    hrefs = re.findall(r'class="about-try"[^>]*?href="([^"]+)"', html.replace("\n", " "))
    assert hrefs == [
        "/?scenario=uri_2021&amp;at=2021-02-16T15:00Z",
        "/demo/patient-view?facility=vha_648",
        "/card-library",
    ], hrefs
    assert "card=" not in hrefs[0]
    for href in hrefs:
        assert client.get(href.replace("&amp;", "&")).status_code == 200, href
    from xevents.providers.replay import list_scenarios

    assert "uri_2021" in set(list_scenarios())
    assert "outage-dialysis" in {c.id for c in load_cards(CARDS_DIR)}


def test_welcome_script_remembers_and_tours(client: TestClient) -> None:
    """Structural guard on welcome.js: the dismissal key, the four tour steps and the Monitor
    selectors they point at. A renamed selector would leave the tour ringing nothing."""
    js = client.get("/static/welcome.js").text
    for name in (
        "function openWelcome",
        "function dismissWelcome",
        "function showHint",
        "function startTour",
        "function endTour",
        "function stepTour",
        "function drawTour",
        "function placeCard",
        "function targetRect",
    ):
        assert name in js, name
    assert '"mxe.welcome.seen"' in js
    assert js.count("title:") == 4, "four tour steps"
    monitor = client.get("/").text
    for selector, marker in (
        (".grp.transport", 'class="grp transport"'),
        (".clock-grp", 'class="clock-grp"'),
        ("#map-wrap", 'id="map-wrap"'),
        ("#side", 'id="side"'),
        ("footer.timeline", '<footer class="timeline">'),
    ):
        assert selector in js, selector
        assert marker in monitor, marker


def test_welcome_styles_exist_for_the_dialog_and_the_tour(client: TestClient) -> None:
    """The dialog blurs the app behind it and the tour cuts a hole in its own dim layer; both
    live in app.css, since the templates carry no style attributes of their own."""
    css = client.get("/static/app.css").text
    for rule in (
        "dialog.about-dialog",
        "dialog.about-dialog::backdrop",
        "body.welcome-open >",
        ".about-pill",
        ".about-hint",
        ".tour-dim",
        ".tour-ring",
        ".tour-card",
        "@media (max-height:800px)",
    ):
        assert rule in css, rule


def test_boundary_files_revalidate_instead_of_redownloading(client: TestClient) -> None:
    """The map's boundary files are the largest thing the demo sends (about 1.3 MB gzipped,
    ~18 s on the free hosted instance). They are cacheable for a day; when that lapses the
    browser must be able to revalidate, or it downloads the whole file again to be told it
    has not changed."""
    for path in ("/reference/counties", "/reference/states", "/reference/countries"):
        r = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200, path
        assert "max-age=86400" in r.headers["cache-control"], path
        etag = r.headers.get("etag")
        assert etag and r.headers.get("last-modified"), path
        again = client.get(path, headers={"Accept-Encoding": "gzip", "If-None-Match": etag})
        assert again.status_code == 304, path
        assert not again.content, path
        assert again.headers.get("etag") == etag, path
        # a stale validator still gets the body
        fresh = client.get(path, headers={"Accept-Encoding": "gzip", "If-None-Match": '"nope"'})
        assert fresh.status_code == 200 and fresh.content, path


def test_gzip_and_identity_do_not_share_an_etag(client: TestClient) -> None:
    """One URL, two representations. Handing the gzip body's validator to a client that asked
    for identity (or the reverse) would answer 304 for a body it has never seen."""
    gz = client.get("/reference/states", headers={"Accept-Encoding": "gzip"}).headers["etag"]
    plain = client.get("/reference/states", headers={"Accept-Encoding": "identity"}).headers["etag"]
    assert gz != plain
    crossed = client.get(
        "/reference/states", headers={"Accept-Encoding": "identity", "If-None-Match": gz}
    )
    assert crossed.status_code == 200


def test_counties_are_served_at_map_precision_but_joined_at_full(client: TestClient) -> None:
    """Two copies on purpose. The browser gets outlines only, rounded to ~110 m — finer than a
    pixel at national zoom. ``CountyIndex`` keeps ray-casting facilities against the full file,
    so thinning what the map draws can never move a facility into another county."""
    import json

    from xevents.api import COUNTIES_DISPLAY_GEOJSON, COUNTIES_GEOJSON

    served = client.get("/reference/counties").json()
    full = json.loads(COUNTIES_GEOJSON.read_text(encoding="utf-8"))
    assert [f["id"] for f in served["features"]] == [f["id"] for f in full["features"]]
    # map.js styles by feature.id; bbox and properties are the server's, and are not sent
    assert all("bbox" not in f and "properties" not in f for f in served["features"])
    assert all("bbox" in f and "properties" in f for f in full["features"]), (
        "the join file keeps what CountyIndex reads"
    )
    assert COUNTIES_DISPLAY_GEOJSON.stat().st_size < COUNTIES_GEOJSON.stat().st_size
    assert CountyIndex.load().source, "the index still loads the full file"
    js = client.get("/static/map.js").text
    assert 'fetch("/reference/counties")' in js and "feature.id" in js
