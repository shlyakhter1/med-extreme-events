"""Ingest events into the event store.

``EVENT_MODE=replay`` (default): load every scenario under ``fixtures/events/`` (or
``--scenario NAME``), replacing that scenario's rows. ``EVENT_MODE=live``: pull current NWS
alerts, OpenFEMA declarations, HMS smoke (last 2 days), the EAGLE-I county outage snapshot
(threshold = the lowest ``outage_pct_min`` any card asks for; needs ``EAGLEI_TOKEN`` for the
FEMA partner service or a public mirror in ``EAGLEI_FEATURE_URL``) and, when
``AIRNOW_API_KEY`` is set, AirNow observations for the next 7 days' window; upsert by natural
key. Both modes land in the same ``events`` table.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from xevents.cards import load_cards
from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.models import Event, TimeWindow
from xevents.providers.airnow import AirNowProvider
from xevents.providers.base import ProviderError
from xevents.providers.eagle_i import EagleIProvider, load_customers, min_outage_pct
from xevents.providers.hms import HMSSmokeProvider
from xevents.providers.iem_archive import IEMArchiveProvider
from xevents.providers.nws import NWSAlertsProvider
from xevents.providers.openfema import OpenFEMAProvider
from xevents.providers.replay import list_scenarios, load_scenario
from xevents.store import (
    delete_scenario_events,
    init_db,
    list_events,
    make_engine,
    upsert_events,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_RAW = REPO_ROOT / "fixtures" / "live" / "raw"


def ingest_replay(engine: object, scenario: str | None) -> int:
    names = [scenario] if scenario else list_scenarios()
    if not names:
        print("no scenarios found under fixtures/events/", file=sys.stderr)
        return 1
    for name in names:
        events = load_scenario(name)
        removed = delete_scenario_events(engine, name)  # type: ignore[arg-type]
        n = upsert_events(engine, events)  # type: ignore[arg-type]
        print(f"replay {name}: {n} events loaded (replaced {removed})")
    return 0


def _signature(e: Event) -> tuple[str, tuple[str, ...], str]:
    counties = tuple(sorted(e.geography.county_fips))
    return (e.event_name, counties, e.onset.strftime("%Y-%m-%dT%H"))


def dedupe(events: list[Event], existing: list[Event] | None = None) -> tuple[list[Event], int]:
    """Drop archive copies of alerts the live CAP feed already gave us — in this run or in
    an earlier one.

    The same warning can arrive twice: once from ``/alerts/active`` (authoritative for what
    is in force now) and once from the archive backfill. They carry different ids, so the
    natural key cannot catch it. Match on what actually identifies the alert instead —
    product name, counties and onset hour — and keep the first, which is the live copy.
    ``existing`` are the store's live CAP rows: once an alert leaves ``/alerts/active`` the
    archive still carries it for two weeks, and without this seed every alert ended up
    stored twice.
    """
    seen: set[tuple[str, tuple[str, ...], str]] = {
        _signature(e) for e in (existing or []) if e.source_id.startswith("urn:oid:")
    }
    kept: list[Event] = []
    for e in events:
        sig = _signature(e)
        if sig in seen:
            continue
        seen.add(sig)
        kept.append(e)
    return kept, len(events) - len(kept)


def ingest_live(engine: object, days_ahead: int, lookback_days: int) -> int:
    now = datetime.now(UTC)
    window = TimeWindow(
        start=now - timedelta(days=lookback_days), end=now + timedelta(days=days_ahead)
    )
    counties = CountyIndex.load()
    resolver = UgcResolver.load()
    events: list[Event] = []
    failures = 0

    # Ordered: the live CAP feed first, so de-duplication keeps it over the archive copy.
    providers: list[tuple[str, Any, TimeWindow]] = [
        ("nws (active)", lambda: NWSAlertsProvider(resolver, raw_dir=LIVE_RAW), window),
        (
            f"nws (archive, {lookback_days}d)",
            lambda: IEMArchiveProvider(resolver, raw_dir=LIVE_RAW),
            TimeWindow(start=now - timedelta(days=lookback_days), end=now),
        ),
        ("openfema", lambda: OpenFEMAProvider(raw_dir=LIVE_RAW), window),
        (
            "hms",
            lambda: HMSSmokeProvider(counties, raw_dir=LIVE_RAW),
            TimeWindow(start=now - timedelta(days=2), end=now),
        ),
    ]
    outage_threshold = min_outage_pct(load_cards())
    eaglei_configured = bool(os.environ.get("EAGLEI_TOKEN") or os.environ.get("EAGLEI_FEATURE_URL"))
    if outage_threshold is not None and not eaglei_configured:
        print(
            "eagle_i: skipped (FEMA's partner layer is token-gated; set EAGLEI_TOKEN, or "
            "EAGLEI_FEATURE_URL to a public EAGLE-I mirror)"
        )
    elif outage_threshold is not None:
        providers.append(
            (
                "eagle_i",
                lambda: EagleIProvider(
                    load_customers(), threshold_pct=outage_threshold, raw_dir=LIVE_RAW
                ),
                window,
            )
        )
    if os.environ.get("AIRNOW_API_KEY"):
        providers.append(
            (
                "airnow",
                lambda: AirNowProvider(counties, raw_dir=LIVE_RAW),
                TimeWindow(start=now - timedelta(hours=6), end=now),
            )
        )
    else:
        print("airnow: skipped (AIRNOW_API_KEY not set)")

    for name, factory, w in providers:
        # One feed must never take the others down: transport errors (httpx exceptions are
        # not OSError), malformed JSON and validation errors are all caught per provider.
        try:
            provider = factory()
            got = provider.fetch(w)
            provider.close()
        except (ProviderError, OSError, httpx.HTTPError, ValueError) as exc:
            failures += 1
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        print(f"{name}: {len(got)} events")
        events.extend(got)

    stored_live = [e for e in list_events(engine, source="nws") if e.scenario is None]  # type: ignore[arg-type]
    events, dropped = dedupe(events, existing=stored_live)
    if dropped:
        print(f"de-duplicated {dropped} duplicate copies of the same NWS alerts")
    n = upsert_events(engine, events)  # type: ignore[arg-type]
    print(f"live: {n} events upserted from {len(providers) - failures}/{len(providers)} providers")
    return 1 if failures == len(providers) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["replay", "live"], default=os.environ.get("EVENT_MODE", "replay")
    )
    parser.add_argument("--scenario", default=None, help="replay only: a single scenario")
    parser.add_argument("--days-ahead", type=int, default=7)
    parser.add_argument(
        "--lookback-days", type=int, default=14, help="live: how much recent weather to load"
    )
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    engine = make_engine(args.database_url)
    init_db(engine)
    if args.mode == "replay":
        return ingest_replay(engine, args.scenario)
    return ingest_live(engine, args.days_ahead, args.lookback_days)


if __name__ == "__main__":
    sys.exit(main())
