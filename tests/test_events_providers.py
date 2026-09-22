"""Event providers: parsers against saved raw payloads (network boundary only)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import STATE_FIPS, UgcResolver
from xevents.geography.polygons import counties_covered
from xevents.models import (
    CapSeverity,
    Event,
    EventGeography,
    EventSource,
    EventType,
    Temporality,
    TimeWindow,
)
from xevents.providers.airnow import parse_observations
from xevents.providers.base import ProviderError
from xevents.providers.hms import parse_smoke
from xevents.providers.nws import (
    NWS_EVENT_TYPES,
    NWSAlertsProvider,
    normalize_nws_event,
    parse_alert,
    parse_alerts,
)
from xevents.providers.openfema import parse_declarations

FIX = Path(__file__).parent / "fixtures" / "events"


@pytest.fixture(scope="module")
def counties() -> CountyIndex:
    return CountyIndex.load()


@pytest.fixture(scope="module")
def resolver() -> UgcResolver:
    return UgcResolver.load()


# --------------------------------------------------------------------------- NWS


def test_ugc_resolver_counties_and_zones(resolver: UgcResolver) -> None:
    assert resolver.counties("WVC013") == ["54013"]
    assert resolver.counties("NYZ072") == ["36061"]  # Manhattan public zone
    assert resolver.counties("XXZ999") == []
    assert STATE_FIPS["FL"] == "12"
    fips, note = resolver.resolve(["WVC013"], ["054013", "054017"])
    assert fips == ["54013", "54017"]
    assert "SAME" in note


def test_parse_live_alert_sample(resolver: UgcResolver) -> None:
    doc = json.loads((FIX / "nws_alerts_active_sample.json").read_text(encoding="utf-8"))
    events = parse_alerts(doc, resolver, raw_ref="sample")
    names = {e.event_name for e in events}
    assert names == {"Flash Flood Warning", "Heat Advisory", "Flood Watch"}, (
        "Small Craft Advisory is not tracked"
    )
    ffw = next(e for e in events if e.event_name == "Flash Flood Warning")
    assert ffw.event_type is EventType.HURRICANE_FLOOD
    assert ffw.severity is CapSeverity.SEVERE
    assert ffw.geography.county_fips[:2] == ["54013", "54017"]
    assert ffw.geography.polygon is not None and ffw.geography.polygon["type"] == "Polygon"
    assert ffw.onset.tzinfo is not None and ffw.expires >= ffw.onset
    heat = next(e for e in events if e.event_name == "Heat Advisory")
    assert heat.event_type is EventType.HEAT
    assert heat.geography.ugc and heat.geography.ugc[0][2] == "Z"
    assert heat.geography.county_fips, "zone-based alert must resolve to counties"
    assert heat.event_key == f"nws:{heat.source_id}"


def test_nws_provider_requires_user_agent(
    monkeypatch: pytest.MonkeyPatch, resolver: UgcResolver
) -> None:
    monkeypatch.delenv("NWS_USER_AGENT", raising=False)
    with pytest.raises(ProviderError, match="NWS_USER_AGENT"):
        NWSAlertsProvider(resolver)


def test_nws_provider_fetch_filters_window(resolver: UgcResolver, tmp_path: Path) -> None:
    doc = json.loads((FIX / "nws_alerts_active_sample.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("test-agent")
        assert request.url.path == "/alerts/active"
        assert request.url.params["status"] == "actual"
        return httpx.Response(200, json=doc)

    provider = NWSAlertsProvider(
        resolver,
        user_agent="test-agent (x@y)",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    window = TimeWindow(
        start=datetime(2026, 9, 20, tzinfo=UTC), end=datetime(2026, 9, 27, tzinfo=UTC)
    )
    events = provider.fetch(window)
    provider.close()
    assert len(events) == 3
    assert list(tmp_path.glob("nws_alerts_active_*.json"))
    far = TimeWindow(start=datetime(2030, 1, 1, tzinfo=UTC), end=datetime(2030, 1, 2, tzinfo=UTC))
    assert (
        NWSAlertsProvider(
            resolver, user_agent="test-agent", transport=httpx.MockTransport(handler)
        ).fetch(far)
        == []
    )


# --------------------------------------------------------------------------- HMS


def test_polygon_county_coverage(counties: CountyIndex) -> None:
    # A box around downtown Portland → Multnomah (and maybe neighbours), never Florida.
    box = {
        "type": "Polygon",
        "coordinates": [
            [[-122.75, 45.45], [-122.55, 45.45], [-122.55, 45.6], [-122.75, 45.6], [-122.75, 45.45]]
        ],
    }
    covered = counties_covered(box, counties)
    assert "41051" in covered
    assert all(c.startswith(("41", "53")) for c in covered)
    assert counties_covered({"type": "Point", "coordinates": [0, 0]}, counties) == []


def test_parse_hms_smoke_day(counties: CountyIndex) -> None:
    data = (FIX / "hms_smoke20230607.zip").read_bytes()
    events = parse_smoke(data, date(2023, 6, 7), counties, raw_ref="hms")
    by_density = {e.metrics["smoke_density"]: e for e in events}
    assert set(by_density) <= {"Light", "Medium", "Heavy"}
    heavy = by_density["Heavy"]
    assert heavy.event_type is EventType.WILDFIRE_SMOKE
    assert heavy.severity is CapSeverity.SEVERE
    assert heavy.source_id == "2023-06-07:heavy"
    assert "36061" in heavy.geography.county_fips, "June 7 2023 heavy smoke covered Manhattan"
    assert heavy.onset.date() == date(2023, 6, 7)
    assert heavy.geography.polygon is not None and heavy.geography.polygon["type"] == "MultiPolygon"
    assert sum(int(e.metrics["polygon_count"]) for e in events) == 88


# --------------------------------------------------------------------------- OpenFEMA


def test_parse_openfema_ian() -> None:
    rows = json.loads((FIX / "openfema_ian_4673.json").read_text(encoding="utf-8"))[
        "DisasterDeclarationsSummaries"
    ]
    events = parse_declarations(rows, raw_ref="fema")
    assert len(events) == 1
    ian = events[0]
    assert ian.source is EventSource.OPENFEMA and ian.source_id == "4673"
    assert ian.event_type is EventType.HURRICANE_FLOOD
    assert ian.headline == "HURRICANE IAN"
    assert len(ian.geography.county_fips) == 67
    assert "12071" in ian.geography.county_fips  # Lee County
    assert ian.onset == datetime(2022, 9, 23, tzinfo=UTC)
    assert ian.metrics["fema_disaster_number"] == 4673
    assert ian.geography.states == ["FL"]


# --------------------------------------------------------------------------- AirNow


def test_parse_airnow_observations(counties: CountyIndex) -> None:
    rows: list[dict[str, Any]] = [
        {
            "Latitude": 40.7128,
            "Longitude": -74.0060,
            "UTC": "2023-06-07T18:00",
            "Parameter": "PM2.5",
            "AQI": 342,
            "Category": 5,
            "SiteName": "NYC",
        },
        {
            "Latitude": 40.7128,
            "Longitude": -74.0060,
            "UTC": "2023-06-07T17:00",
            "Parameter": "PM2.5",
            "AQI": 300,
            "Category": 5,
            "SiteName": "NYC",
        },
        {
            "Latitude": 45.5,
            "Longitude": -122.68,
            "UTC": "2023-06-07T18:00",
            "Parameter": "OZONE",
            "AQI": 42,
            "Category": 1,
            "SiteName": "PDX",
        },
        {
            "Latitude": 0.0,
            "Longitude": 0.0,
            "UTC": "2023-06-07T18:00",
            "Parameter": "PM2.5",
            "AQI": 500,
            "Category": 6,
        },
        {"Latitude": "bad", "AQI": "x"},
    ]
    events = parse_observations(rows, counties)
    assert len(events) == 1
    e = events[0]
    assert e.event_type is EventType.AIR_POLLUTION
    assert e.geography.county_fips == ["36061"]
    assert e.metrics["aqi"] == 342, "max AQI per county/parameter wins"
    assert e.severity is CapSeverity.SEVERE
    assert e.source_id == "2023-06-07:36061:pm2.5"


# --------------------------------------------------------------------------- IEM archive


def test_parse_iem_archive_sample(resolver: UgcResolver) -> None:
    """The archive backfills recent NWS products; they must land in the same Event model."""
    from xevents.providers.iem_archive import parse_iem_csv

    events = parse_iem_csv(FIX / "iem_watchwarn_sample.csv", resolver, scenario=None)
    assert events
    assert all(e.source is EventSource.NWS for e in events), "archived NWS products stay NWS"
    assert all(e.scenario is None for e in events), "live events carry no scenario"
    assert all(e.metrics["retrieval"] == "iem_vtec_archive" for e in events)
    assert all(e.geography.county_fips for e in events), "every archived alert resolves"
    names = {e.event_name for e in events}
    assert names <= set(NWS_EVENT_TYPES), names
    for e in events:
        assert e.expires >= e.onset
        assert e.event_key.startswith("nws:")


def test_live_dedupe_drops_archive_copies_of_active_alerts() -> None:
    """The same warning arrives from CAP and from the archive under different ids; only the
    live copy should survive."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ingest", Path(__file__).parents[1] / "scripts" / "ingest.py"
    )
    assert spec and spec.loader
    ingest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest)

    onset = datetime(2026, 9, 20, 6, 30, tzinfo=UTC)
    common = {
        "event_type": EventType.HEAT,
        "event_name": "Heat Advisory",
        "temporality": Temporality.IMMINENT,
        "onset": onset,
        "expires": onset + timedelta(hours=12),
        "geography": EventGeography(county_fips=["41051", "53033"]),
    }
    live = Event(source=EventSource.NWS, source_id="urn:oid:cap-1", **common)
    archived = Event(source=EventSource.NWS, source_id="2026-KPQR-HT.Y-0007", **common)
    other = Event(
        source=EventSource.NWS,
        source_id="2026-KPQR-HT.Y-0008",
        **{**common, "geography": EventGeography(county_fips=["12071"])},
    )

    kept, dropped = ingest.dedupe([live, archived, other])
    assert dropped == 1
    assert [e.source_id for e in kept] == ["urn:oid:cap-1", "2026-KPQR-HT.Y-0008"]
    assert ingest.dedupe([live])[1] == 0
    # a later run: the alert has left /alerts/active but the archive still carries it, and
    # the store already holds the CAP copy → the archive copy is dropped against the store
    kept, dropped = ingest.dedupe([archived, other], existing=[live])
    assert dropped == 1 and [e.source_id for e in kept] == ["2026-KPQR-HT.Y-0008"]
    # a stored archive copy does not seed the filter (only CAP rows are authoritative)
    assert ingest.dedupe([live], existing=[archived])[1] == 0


# --------------------------------------------------------------------------- temporality


def test_live_alerts_carry_temporality(resolver: UgcResolver) -> None:
    doc = json.loads((FIX / "nws_alerts_active_sample.json").read_text(encoding="utf-8"))
    by_name = {e.event_name: e for e in parse_alerts(doc, resolver)}
    assert by_name["Flood Watch"].temporality is Temporality.FORECAST
    assert by_name["Flash Flood Warning"].temporality is Temporality.IMMINENT
    assert by_name["Heat Advisory"].temporality is Temporality.IMMINENT
    assert all("temporality_basis" in e.metrics for e in by_name.values())
    # CAP certainty=Observed wins over the product suffix
    feature = next(f for f in doc["features"] if f["properties"]["event"] == "Flash Flood Warning")
    observed = json.loads(json.dumps(feature))
    observed["properties"]["certainty"] = "Observed"
    ev = parse_alert(observed, resolver)
    assert ev is not None and ev.temporality is Temporality.OBSERVED
    assert ev.metrics["temporality_basis"] == "cap certainty=Observed"


def test_legacy_cold_product_names_are_normalized(resolver: UgcResolver) -> None:
    """NWS SCN23-44 renamed the cold products; archived alerts carry the old names. The
    provider normalizes before matching and keeps the raw name; the current names are the
    tracked ones (Card 7)."""
    assert normalize_nws_event("Wind Chill Warning") == (
        "Extreme Cold Warning",
        "Wind Chill Warning",
    )
    assert normalize_nws_event("Wind Chill Watch") == ("Extreme Cold Watch", "Wind Chill Watch")
    assert normalize_nws_event("Wind Chill Advisory") == (
        "Cold Weather Advisory",
        "Wind Chill Advisory",
    )
    assert normalize_nws_event("Hard Freeze Warning") == ("Freeze Warning", "Hard Freeze Warning")
    assert normalize_nws_event("Heat Advisory") == ("Heat Advisory", None)
    doc = json.loads((FIX / "nws_alerts_active_sample.json").read_text(encoding="utf-8"))
    feature = json.loads(
        json.dumps(next(f for f in doc["features"] if f["properties"]["event"] == "Heat Advisory"))
    )
    feature["properties"]["event"] = "Wind Chill Warning"
    ev = parse_alert(feature, resolver)
    assert ev is not None
    assert ev.event_type is EventType.EXTREME_COLD
    assert ev.event_name == "Extreme Cold Warning", "matched under the current name"
    assert ev.metrics["raw_nws_event"] == "Wind Chill Warning"
    assert ev.temporality is Temporality.IMMINENT
    feature["properties"]["event"] = "Hard Freeze Warning"
    assert parse_alert(feature, resolver) is None, "Freeze Warning is normalized but not tracked"
    assert "Wind Chill Warning" not in NWS_EVENT_TYPES


def test_other_providers_map_temporality(counties: CountyIndex) -> None:
    rows = json.loads((FIX / "openfema_ian_4673.json").read_text(encoding="utf-8"))[
        "DisasterDeclarationsSummaries"
    ]
    assert parse_declarations(rows)[0].temporality is Temporality.OBSERVED
    smoke = parse_smoke((FIX / "hms_smoke20230607.zip").read_bytes(), date(2023, 6, 7), counties)
    assert smoke and all(e.temporality is Temporality.OBSERVED for e in smoke)
    obs_rows: list[dict[str, Any]] = [
        {
            "Latitude": 40.7128,
            "Longitude": -74.0060,
            "UTC": "2023-06-07T18:00",
            "Parameter": "PM2.5",
            "AQI": 200,
            "Category": 4,
            "SiteName": "NYC",
        }
    ]
    assert parse_observations(obs_rows, counties)[0].temporality is Temporality.OBSERVED
    forecast = parse_observations(obs_rows, counties, product="forecast")[0]
    assert forecast.temporality is Temporality.FORECAST
    assert forecast.metrics["temporality_basis"] == "airnow forecast"


def test_live_ingest_isolates_a_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timeout on one feed (httpx errors are not OSError) must not abort the run: the
    other providers still run and their events are stored."""
    import importlib.util

    from xevents.store import init_db, list_events, make_engine

    spec = importlib.util.spec_from_file_location(
        "ingest", Path(__file__).parents[1] / "scripts" / "ingest.py"
    )
    assert spec and spec.loader
    ingest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingest)

    class Boom:
        def fetch(self, window: TimeWindow) -> list[Event]:
            raise httpx.ConnectTimeout("api.weather.gov timed out")

        def close(self) -> None:
            pass

    class Fine:
        def fetch(self, window: TimeWindow) -> list[Event]:
            onset = window.start
            return [
                Event(
                    source=EventSource.HMS,
                    source_id="ok",
                    event_type=EventType.WILDFIRE_SMOKE,
                    event_name="HMS smoke (Heavy)",
                    temporality=Temporality.OBSERVED,
                    onset=onset,
                    expires=onset + timedelta(hours=1),
                    geography=EventGeography(county_fips=["41051"]),
                )
            ]

        def close(self) -> None:
            pass

    monkeypatch.setattr(ingest, "NWSAlertsProvider", lambda *a, **k: Boom())
    monkeypatch.setattr(ingest, "IEMArchiveProvider", lambda *a, **k: Boom())
    monkeypatch.setattr(ingest, "OpenFEMAProvider", lambda *a, **k: Boom())
    monkeypatch.setattr(ingest, "HMSSmokeProvider", lambda *a, **k: Fine())
    monkeypatch.setattr(ingest, "EagleIProvider", lambda *a, **k: Boom())
    monkeypatch.setattr(ingest, "load_customers", lambda: {})
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    engine = make_engine(f"sqlite:///{tmp_path / 'live.db'}")
    init_db(engine)
    rc = ingest.ingest_live(engine, days_ahead=1, lookback_days=1)
    assert rc == 0, "some providers succeeded"
    stored = [e for e in list_events(engine) if e.scenario is None]
    assert [e.event_key for e in stored] == ["hms:ok"]


def test_openfema_pages_until_a_short_page() -> None:
    from xevents.providers.openfema import PAGE, OpenFEMAProvider

    rows = json.loads((FIX / "openfema_ian_4673.json").read_text(encoding="utf-8"))[
        "DisasterDeclarationsSummaries"
    ]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params["$skip"])
        calls.append(skip)
        assert request.url.params["$top"] == str(PAGE)
        if skip == 0:  # a full first page forces a second request
            return httpx.Response(
                200, json={"DisasterDeclarationsSummaries": rows * (PAGE // len(rows) + 1)}
            )
        return httpx.Response(200, json={"DisasterDeclarationsSummaries": rows})

    provider = OpenFEMAProvider(transport=httpx.MockTransport(handler))
    window = TimeWindow(
        start=datetime(2022, 9, 20, tzinfo=UTC), end=datetime(2022, 10, 5, tzinfo=UTC)
    )
    events = provider.fetch(window)
    provider.close()
    assert calls == [0, PAGE], "second page requested with $skip"
    assert [e.source_id for e in events] == ["4673"], "rows group by disaster number"


def test_malformed_alert_is_skipped_not_fatal(resolver: UgcResolver) -> None:
    doc = json.loads((FIX / "nws_alerts_active_sample.json").read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(doc))
    bad = broken["features"][0]
    for k in ("onset", "effective", "sent", "ends", "expires"):
        bad["properties"][k] = None
    events = parse_alerts(broken, resolver)
    assert len(events) == len(parse_alerts(doc, resolver)) - (
        1 if bad["properties"]["event"] in NWS_EVENT_TYPES else 0
    )


def test_state_abbreviations_cover_territories() -> None:
    from xevents.providers.eagle_i import STATE_ABBR

    for name, abbr in (
        ("Guam", "GU"),
        ("Virgin Islands", "VI"),
        ("American Samoa", "AS"),
        ("Northern Mariana Islands", "MP"),
        ("Puerto Rico", "PR"),
    ):
        assert STATE_ABBR[name] == abbr


def test_empower_builder_refuses_swapped_layers() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_empower", Path(__file__).parents[1] / "scripts" / "build_empower.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.expect_layer_name(mod.COUNTY_LAYER, "Electricity Dependent DME – ALL – CountyLevel")
    with pytest.raises(SystemExit, match="expected a county-level layer"):
        mod.expect_layer_name(mod.COUNTY_LAYER, "Electricity Dependent DME – ALL – ZipLevel")
