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
from xevents.providers.replay import load_scenario
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


def test_dashboard_replay_heat_dome(client: TestClient) -> None:
    r = client.get("/", params={"scenario": "heat_dome_2021", "at": AT})
    assert r.status_code == 200
    html = r.text
    assert "Event board" in html and "Portland VA Medical Center" in html
    assert "Excessive Heat Warning" in html
    assert "Replay" in html and "heat_dome_2021" in html
    assert "/dashboard/facilities/vha_648" in html


def test_dashboard_defaults_to_peak_hour(client: TestClient) -> None:
    r = client.get("/", params={"scenario": "ian_2022"})
    assert r.status_code == 200
    assert "Bay Pines" in r.text or "Orlando" in r.text or "Tampa" in r.text
    assert 'value="2022-09-2' in r.text  # as-of defaulted inside the scenario window


def test_dashboard_live_mode_has_freshness_banner(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Live mode" in r.text and "no live events ingested yet" in r.text
    assert "absence of items is not an all-clear" in r.text
    assert client.get("/", params={"scenario": "nope"}).status_code == 404


def test_facility_page_roles_and_acknowledge(client: TestClient) -> None:
    r = client.get("/dashboard/facilities/vha_648", params={"scenario": "heat_dome_2021", "at": AT})
    assert r.status_code == 200
    html = r.text
    assert "Extreme Heat × Bipolar Disorder on Lithium" in html
    assert "Generate the lithium roster" in html, "clinician checklist rendered verbatim"
    assert "how was this number computed?" in html and "veterans × rate (test)" in html
    assert "Acknowledge" in html
    patient = client.get(
        "/dashboard/facilities/vha_648/cards",
        params={"scenario": "heat_dome_2021", "at": AT, "role": "patient"},
    )
    assert patient.status_code == 200
    assert "Heat can push your lithium to a dangerous level." in patient.text
    assert "stop your medication" in patient.text  # apostrophe is HTML-escaped
    caregiver = client.get(
        "/dashboard/facilities/vha_648/cards",
        params={"scenario": "heat_dome_2021", "at": AT, "role": "caregiver"},
    )
    assert "No caregiver content" in caregiver.text
    item_id = html.split('hx-post="/dashboard/action-items/')[1].split("/status")[0]
    ack = client.post(
        f"/dashboard/action-items/{item_id}/status", params={"status": "acknowledged"}
    )
    assert ack.status_code == 200 and "acknowledged" in ack.text
    again = client.get(
        "/dashboard/facilities/vha_648", params={"scenario": "heat_dome_2021", "at": AT}
    )
    assert "Mark completed" in again.text
    assert (
        client.post(
            f"/dashboard/action-items/{item_id}/status", params={"status": "issued"}
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/dashboard/facilities/vha_nope", params={"scenario": "heat_dome_2021"}
        ).status_code
        == 404
    )


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
        r = client.get("/", params={"scenario": "heat_dome_2021", "at": value})
        assert r.status_code == 200, f"{value!r} → {r.status_code} {r.text[:120]}"
    assert client.get("/", params={"at": "nonsense"}).status_code == 422
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
    html = client.get("/", params={"scenario": "heat_dome_2021", "at": "2021-06-28T00:00"}).text
    assert 'type="datetime-local" name="at" value="2021-06-28T00:00"' in html


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
    dash = client.get("/", params=base).text
    assert "<th>Where</th>" in dash


def test_playback_offers_live_and_navigation(client: TestClient) -> None:
    """You must be able to get from playback back to live without editing the URL."""
    html = client.get("/playback").text
    js = client.get("/static/playback.js").text
    assert "if (!onsets.length)" in js and "no live events ingested yet" in js, (
        "live mode with no events must not compute Math.min() of nothing"
    )
    assert 'id="nav-dashboard"' in html and 'id="nav-events"' in html
    assert 'id="scenario"' in html
    js = client.get("/static/playback.js").text
    assert 'value="live"' in js, "the view selector offers live"
    assert "Cards firing now" in js, "cards are surfaced in playback, not only on the dashboard"
    assert "selectCard" in js and "cardColor" in js, "cards can be selected and shown on the map"
    assert client.get("/playback", params={"scenario": "ian_2022"}).status_code == 200


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

    page = client.get("/playback").text
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

    for path in ("/", "/playback"):
        page = client.get(path).text
        assert 'id="map-legend"' in page, path
    dash = client.get("/", params={"scenario": "heat_dome_2021"}).text
    assert "XMap.legendHtml" in dash and "no card firing" in dash


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


def test_carbon_panel_on_the_facility_page(client: TestClient) -> None:
    base = {"scenario": "heat_dome_2021", "at": AT}
    html = client.get("/dashboard/facilities/vha_648", params=base).text
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
    dash = client.get("/", params={"scenario": "heat_dome_2021", "at": AT}).text
    assert "XMap.fitPoints(ctx, bounds" in dash


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
    html = c.get("/").text
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
    assert "/playback?scenario=uri_2021" in html, "replays carrying EAGLE-I are computed"
    assert "facilities" in html and "stations" in html
    backlog = load_backlog()
    assert backlog and all(b.id in html for b in backlog), "backlog comes from hazard_sources"
    assert 'href="/sources' in c.get("/").text, "the tab is in the shared header"
    assert 'href="/sources"' in c.get("/playback").text
    # every live provider name in the registry is one that ingest actually records
    ingest = (Path(__file__).resolve().parents[1] / "scripts" / "ingest.py").read_text()
    for s in registry.sources:
        for name in s.live.runs:
            stem = name.split(" (")[0]
            assert f'"{stem}' in ingest or f"'{stem}" in ingest, name
