"""EAGLE-I outage provider (M7): ArcGIS snapshot parsing, ORNL replay slices, the Moehl
customer denominator, percent-out events, and the two-poll debounce end to end."""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from xevents.api import create_app
from xevents.cards import CARDS_DIR, load_cards
from xevents.engine import match
from xevents.models import (
    CapSeverity,
    Card,
    Estimate,
    EventSource,
    EventType,
    Facility,
    OperatingStatusCode,
    Role,
    Temporality,
    TimeWindow,
)
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.base import ProviderError
from xevents.providers.eagle_i import (
    ATTRIBUTION,
    CUSTOMERS_CAVEAT,
    EagleIProvider,
    OutagePoll,
    iter_ornl_csv,
    load_customers,
    load_ornl_events,
    min_outage_pct,
    parse_features,
    polls_to_events,
    resample_polls,
    severity_for,
    slice_ornl_csv,
)
from xevents.store import (
    init_db,
    make_engine,
    upsert_action_items,
    upsert_events,
    upsert_facilities,
)

FIX = Path(__file__).parent / "fixtures" / "events"
T0 = datetime(2022, 9, 28, 18, tzinfo=UTC)
LEE, PINELLAS = "12071", "12103"
CUSTOMERS = {LEE: 600_000, PINELLAS: 360_000}


def _poll(fips: str, hour: int, out: int, *, name: str = "Lee", state: str = "FL") -> OutagePoll:
    return OutagePoll(
        county_fips=fips,
        run_start=T0 + timedelta(hours=hour),
        customers_out=out,
        county_name=name,
        state=state,
    )


# --------------------------------------------------------------------------- reference


def test_customer_table_loads_with_padded_fips() -> None:
    customers = load_customers()
    assert len(customers) > 3200
    assert all(len(k) == 5 for k in customers)
    assert customers[LEE] == 628_635, "Lee County FL, MCC 2022"
    assert customers["01001"] == 24_619, "Autauga AL keeps its leading zero"
    assert "Grand Total".zfill(5) not in customers


def test_emit_threshold_is_the_lowest_card_threshold() -> None:
    cards = load_cards(CARDS_DIR)
    assert min_outage_pct(cards) == 10.0
    assert min_outage_pct([c for c in cards if c.number == 3]) == 25.0
    assert min_outage_pct([c for c in cards if c.number == 1]) is None


# --------------------------------------------------------------------------- events


def test_polls_to_events_threshold_metrics_and_streak() -> None:
    polls = [
        _poll(LEE, 0, 30_000),  # 5%  → below threshold
        _poll(LEE, 1, 90_000),  # 15% → event, streak 1
        _poll(LEE, 2, 180_000),  # 30% → event, streak 2
        _poll(LEE, 3, 12_000),  # 2%  → below, streak resets
        _poll(LEE, 4, 66_000),  # 11% → event, streak 1
        _poll(PINELLAS, 1, 200_000, name="Pinellas"),  # 55.6% → Extreme
        _poll("99999", 1, 500),  # no denominator → skipped
    ]
    events = polls_to_events(polls, CUSTOMERS, threshold_pct=10, poll_minutes=60)
    assert [e.source_id for e in events] == [
        f"{LEE}:2022-09-28T1900",
        f"{LEE}:2022-09-28T2000",
        f"{LEE}:2022-09-28T2200",
        f"{PINELLAS}:2022-09-28T1900",
    ]
    first = events[0]
    assert first.source is EventSource.EAGLE_I and first.event_type is EventType.POWER_OUTAGE
    assert first.temporality is Temporality.OBSERVED
    assert first.metrics["customers_out"] == 90_000
    assert first.metrics["county_customers"] == 600_000
    assert first.metrics["outage_pct"] == 15.0
    assert first.metrics["poll_streak"] == 1 and events[1].metrics["poll_streak"] == 2
    assert events[2].metrics["poll_streak"] == 1, "a below-threshold poll resets the streak"
    assert first.expires == first.onset + timedelta(hours=1), "contiguous with the next poll"
    assert first.geography.county_fips == [LEE] and first.geography.states == ["FL"]
    assert "90,000 of 600,000" in (first.headline or "")
    assert first.severity is CapSeverity.MODERATE and events[1].severity is CapSeverity.SEVERE
    assert events[3].severity is CapSeverity.EXTREME
    assert severity_for(9.9) is CapSeverity.MINOR


def test_two_poll_debounce_end_to_end() -> None:
    """A synthetic replay slice: the first qualifying poll issues nothing, the second fires
    Cards 5 and 6 (10%) but not Card 3 (25%); a third poll at 30% then fires Card 3."""
    cards = load_cards(CARDS_DIR)
    profile = load_profile(PROFILES_DIR / "va.yaml")
    facility = Facility(
        id="vha_516",
        name="Bay Pines",
        facility_type="va_health_facility",
        lat=27.8,
        lon=-82.8,
        operating_status=OperatingStatusCode.NORMAL,
        county_fips=LEE,
        visn="8",
        classification="VA Medical Center (VAMC)",
    )

    def panels(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=50.0, formula="test", inputs={})

    polls = [
        _poll(LEE, 0, 90_000),
        _poll(LEE, 1, 90_000),
        _poll(LEE, 2, 180_000),
        _poll(LEE, 3, 180_000),
    ]
    events = polls_to_events(polls, CUSTOMERS, threshold_pct=10, poll_minutes=60)
    assert len(events) == 4
    one = match(events[:1], cards, [facility], profile, panels, now=T0)
    assert one.items == [] and any("sustained 1 poll(s) < 2" in t.reason for t in one.log)
    two = match(events[:2], cards, [facility], profile, panels, now=T0)
    assert {(i.card_id, i.event_key) for i in two.items} == {
        ("outage-insulin", events[1].event_key),
        ("outage-dialysis", events[1].event_key),
    }
    assert all(i.phase.value == "during_event" for i in two.items)
    three = match(events[:3], cards, [facility], profile, panels, now=T0)
    assert {i.card_id for i in three.items if i.event_key == events[2].event_key} == {
        "outage-insulin",
        "outage-dialysis",
    }, "the first poll at 30% starts Card 3's own 25% streak; it does not fire yet"
    four = match(events, cards, [facility], profile, panels, now=T0)
    by_card = {i.card_id: i for i in four.items if i.event_key == events[3].event_key}
    assert set(by_card) == {"outage-insulin", "outage-dialysis", "hurricane-delivery-interruption"}
    assert by_card["hurricane-delivery-interruption"].role in set(Role)
    assert by_card["outage-dialysis"].acuity_rank == 0


# --------------------------------------------------------------------------- live (ArcGIS)


def test_parse_featureserver_sample() -> None:
    doc = json.loads((FIX / "eaglei_featureserver_sample.json").read_text(encoding="utf-8"))
    polls = parse_features(doc["features"])
    assert len(polls) == 6
    p = polls[0]
    assert p.county_fips == "39113" and p.county_name == "Montgomery" and p.state == "OH"
    assert p.customers_out == 1298
    assert p.run_start == datetime(2026, 9, 21, 21, 0, tzinfo=UTC), "epoch ms → UTC"
    assert p.extra["feed_covered_customers"] == 290_690
    assert p.extra["feed_model_count"] == 290_692
    assert all(len(x.county_fips) == 5 for x in polls)
    with pytest.raises(ProviderError, match="expected fields"):
        parse_features([{"attributes": {"countyName": "x"}}])


def test_provider_pages_caches_and_filters(tmp_path: Path) -> None:
    doc = json.loads((FIX / "eaglei_featureserver_sample.json").read_text(encoding="utf-8"))
    pages = [doc["features"][:4], doc["features"][4:]]
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/0/query")
        params = dict(request.url.params)
        seen.append(params)
        assert params["token"] == "t0k", "token travels as a query parameter"
        i = int(params["resultOffset"]) // 4
        return httpx.Response(200, json={"features": pages[i], "exceededTransferLimit": i == 0})

    customers = {p["attributes"]["countyFIPSCode"].__str__(): 300_000 for p in doc["features"]}
    customers["39113"] = 5_000  # Montgomery: 1298/5000 = 26% → qualifies
    provider = EagleIProvider(
        customers,
        threshold_pct=10,
        feature_url="https://example.test/arcgis/rest/services/eagle/FeatureServer/0/",
        token="t0k",
        raw_dir=tmp_path,
        transport=httpx.MockTransport(handler),
    )
    window = TimeWindow(
        start=datetime(2026, 9, 21, tzinfo=UTC), end=datetime(2026, 9, 22, tzinfo=UTC)
    )
    events = provider.fetch(window)
    provider.close()
    assert len(seen) == 2, "follows exceededTransferLimit paging"
    assert [e.source_id for e in events] == ["39113:2026-09-21T2100"]
    assert events[0].metrics["outage_pct"] == 25.96
    assert events[0].raw_ref and Path(events[0].raw_ref).exists()
    assert list(tmp_path.glob("eaglei_outages_*.json"))
    far = TimeWindow(start=datetime(2030, 1, 1, tzinfo=UTC), end=datetime(2030, 1, 2, tzinfo=UTC))
    assert (
        EagleIProvider(
            customers,
            threshold_pct=10,
            feature_url="https://example.test/x/FeatureServer/0",
            token="t0k",
            transport=httpx.MockTransport(handler),
        ).fetch(far)
        == []
    )


def test_provider_explains_token_gated_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": 499, "message": "Token Required"}})

    provider = EagleIProvider(
        {},
        threshold_pct=10,
        feature_url="https://example.test/FeatureServer/0",
        token=None,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderError, match="EAGLEI_TOKEN"):
        provider.fetch_polls()


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("RUN_NETWORK_TESTS"), reason="RUN_NETWORK_TESTS=1")
def test_live_featureserver_contract() -> None:
    """Upstream drift check: the configured layer (FEMA partner service with EAGLEI_TOKEN,
    else EAGLEI_FEATURE_URL, else a public state mirror) must expose the EAGLE-I fields."""
    url = os.environ.get("EAGLEI_FEATURE_URL") or (
        None
        if os.environ.get("EAGLEI_TOKEN")
        else "https://services6.arcgis.com/zxOMWqh0yAD6mMsJ/arcgis/rest/services/"
        "power_outages_eagle_i/FeatureServer/0"
    )
    provider = EagleIProvider(load_customers(), threshold_pct=0, feature_url=url)
    polls, _ = provider.fetch_polls()
    provider.close()
    assert polls, "the snapshot must not be empty"
    assert all(len(p.county_fips) == 5 and p.run_start.tzinfo for p in polls)


# --------------------------------------------------------------------------- replay (ORNL)


def _write_ornl(path: Path, count_col: str) -> None:
    rows: list[list[Any]] = [["fips_code", "county", "state", count_col, "run_start_time"]]
    for minute in range(0, 120, 15):  # eight 15-minute runs over two hours
        when = T0 + timedelta(minutes=minute)
        rows.append(
            ["12071", "Lee", "Florida", 60_000 + minute * 1000, f"{when:%Y-%m-%d %H:%M:%S}"]
        )
        rows.append(["48201", "Harris", "Texas", 5, f"{when:%Y-%m-%d %H:%M:%S}"])
    rows.append(["12071", "Lee", "Florida", 999_999, "2022-10-05 00:00:00"])  # outside the slice
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def test_ornl_loader_slices_and_normalizes(tmp_path: Path) -> None:
    for count_col in ("customers_out", "sum"):  # column name changed across ORNL years
        src = tmp_path / f"eaglei_{count_col}.csv"
        _write_ornl(src, count_col)
        polls = list(iter_ornl_csv(src, states={"Florida"}, start=T0, end=T0 + timedelta(hours=3)))
        assert len(polls) == 8 and {p.county_fips for p in polls} == {"12071"}
        assert polls[0].state == "FL" and polls[0].run_start == T0
        assert polls[1].run_start - polls[0].run_start == timedelta(minutes=15)
    with pytest.raises(ProviderError, match="unexpected ORNL columns"):
        bad = tmp_path / "bad.csv"
        bad.write_text("a,b\n1,2\n", encoding="utf-8")
        list(iter_ornl_csv(bad))
    hourly = resample_polls(polls, 60)
    assert [p.run_start for p in hourly] == [T0, T0 + timedelta(hours=1)]
    assert [p.customers_out for p in hourly] == [105_000, 165_000], "max within the hour"
    dest = tmp_path / "slice.csv"
    assert slice_ornl_csv(src, dest, states={"Florida"}, start=T0, end=T0 + timedelta(hours=3)) == 8
    assert dest.read_text(encoding="utf-8").splitlines()[0] == (
        "fips_code,county,state,customers_out,run_start_time"
    )
    assert list(iter_ornl_csv(dest)) == polls


def test_ornl_replay_events_debounce(tmp_path: Path) -> None:
    src = tmp_path / "eaglei_outages_2022.csv"
    _write_ornl(src, "customers_out")
    events = load_ornl_events(
        src,
        CUSTOMERS,
        threshold_pct=10,
        scenario="ian_2022",
        states={"Florida"},
        start=T0,
        end=T0 + timedelta(hours=3),
        raw_ref="fixtures/x.csv",
    )
    assert [e.source_id for e in events] == ["12071:2022-09-28T1800", "12071:2022-09-28T1900"]
    assert [e.metrics["poll_streak"] for e in events] == [1, 2]
    assert all(e.scenario == "ian_2022" and e.metrics["poll_minutes"] == 60 for e in events)
    native = load_ornl_events(
        src,
        CUSTOMERS,
        threshold_pct=10,
        scenario="ian_2022",
        resample_minutes=None,
        states={"Florida"},
        start=T0,
        end=T0 + timedelta(hours=3),
    )
    assert len(native) == 8 and native[0].expires - native[0].onset == timedelta(minutes=15)


# --------------------------------------------------------------------------- UI


REAL_FACILITIES = Path(__file__).parents[1] / "fixtures" / "reference" / "facilities.geojson"


@pytest.mark.skipif(not REAL_FACILITIES.exists(), reason="run `make reference` first")
def test_outage_renders_with_attribution_and_footnotes(tmp_path: Path) -> None:
    from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
    from xevents.providers.va_facilities import from_geojson

    eng = make_engine(f"sqlite:///{tmp_path / 'outage.db'}")
    init_db(eng)
    raw = from_geojson(json.loads(REAL_FACILITIES.read_text(encoding="utf-8")))
    facilities = attribute_facilities(raw, ZipCountyCrosswalk.load(), CountyIndex.load()).facilities
    upsert_facilities(eng, facilities)
    events = polls_to_events(
        [_poll(LEE, 0, 90_000), _poll(LEE, 1, 90_000)],
        CUSTOMERS,
        threshold_pct=10,
        poll_minutes=60,
    )  # scenario None: a live-mode snapshot, so every live page renders it
    upsert_events(eng, events)
    cards = load_cards(CARDS_DIR)
    profile = load_profile(PROFILES_DIR / "va.yaml")

    def panels(fid: str, card: Card) -> Estimate:
        return Estimate(label="p", value=40.0, formula="veterans × rate (test)", inputs={})

    lee = [f for f in facilities if f.county_fips == LEE]
    assert lee, "Lee County FL has VA facilities"
    result = match(events, cards, lee, profile, panels, now=T0)
    assert result.items
    upsert_action_items(eng, result.items)
    client = TestClient(create_app(eng))
    at = (T0 + timedelta(hours=1, minutes=30)).isoformat()
    key = events[1].event_key

    detail = client.get("/events/detail", params={"key": key}).json()
    assert detail["attribution"] == ATTRIBUTION and CUSTOMERS_CAVEAT in detail["caveats"]
    rows = client.get("/action-items", params={"compact": "1"}).json()
    assert rows["count"] == len(result.items)
    assert rows["items"][0]["event_temporality"] == "observed"
    assert rows["items"][0]["phase"] == "during_event"

    page = client.get(f"/dashboard/events/{key}", params={"at": at})
    assert page.status_code == 200
    assert ATTRIBUTION in page.text and CUSTOMERS_CAVEAT in page.text
    assert "90,000" in page.text and "600,000" in page.text and "15.0%" in page.text
    assert "customers_out ÷ county_customers × 100" in page.text
    assert "not covered" in page.text, "coverage-gap footnote"

    dash = client.get("/", params={"at": at})
    assert dash.status_code == 200
    assert "Power outage (EAGLE-I)" in dash.text and ATTRIBUTION in dash.text
    assert "eagle_i:" in dash.text, "the outage feed shows in the freshness banner"

    fid = result.items[0].scope_id
    facility = client.get(f"/dashboard/facilities/{fid}", params={"at": at})
    assert facility.status_code == 200
    assert ATTRIBUTION in facility.text and "observed → during_event actions" in facility.text
    assert "Hurricane/Power Outage × Dialysis-Dependent ESRD" in facility.text
