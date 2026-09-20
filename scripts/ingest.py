"""Ingest events into the event store.

``EVENT_MODE=replay`` (default): load every scenario under ``fixtures/events/`` (or
``--scenario NAME``), replacing that scenario's rows. ``EVENT_MODE=live``: pull current NWS
alerts, OpenFEMA declarations, HMS smoke (last 2 days) and, when ``AIRNOW_API_KEY`` is set,
AirNow observations for the next 7 days' window; upsert by natural key.
Both modes land in the same ``events`` table.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from xevents.geography.counties import CountyIndex
from xevents.geography.nws_zones import UgcResolver
from xevents.models import Event, TimeWindow
from xevents.providers.airnow import AirNowProvider
from xevents.providers.base import ProviderError
from xevents.providers.hms import HMSSmokeProvider
from xevents.providers.nws import NWSAlertsProvider
from xevents.providers.openfema import OpenFEMAProvider
from xevents.providers.replay import list_scenarios, load_scenario
from xevents.store import delete_scenario_events, init_db, make_engine, upsert_events

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


def ingest_live(engine: object, days_ahead: int) -> int:
    now = datetime.now(UTC)
    window = TimeWindow(start=now - timedelta(days=1), end=now + timedelta(days=days_ahead))
    counties = CountyIndex.load()
    events: list[Event] = []
    failures = 0
    providers: list[tuple[str, object]] = [
        ("nws", lambda: NWSAlertsProvider(UgcResolver.load(), raw_dir=LIVE_RAW)),
        ("openfema", lambda: OpenFEMAProvider(raw_dir=LIVE_RAW)),
        ("hms", lambda: HMSSmokeProvider(counties, raw_dir=LIVE_RAW)),
    ]
    if os.environ.get("AIRNOW_API_KEY"):
        providers.append(("airnow", lambda: AirNowProvider(counties, raw_dir=LIVE_RAW)))
    else:
        print("airnow: skipped (AIRNOW_API_KEY not set)")
    for name, factory in providers:
        try:
            provider = factory()  # type: ignore[operator]
            w = window
            if name == "hms":
                w = TimeWindow(start=now - timedelta(days=2), end=now)
            if name == "airnow":
                w = TimeWindow(start=now - timedelta(hours=6), end=now)
            got = provider.fetch(w)
            provider.close()
        except (ProviderError, OSError) as exc:
            failures += 1
            print(f"{name}: FAILED {exc}", file=sys.stderr)
            continue
        print(f"{name}: {len(got)} events")
        events.extend(got)
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
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    engine = make_engine(args.database_url)
    init_db(engine)
    if args.mode == "replay":
        return ingest_replay(engine, args.scenario)
    return ingest_live(engine, args.days_ahead)


if __name__ == "__main__":
    sys.exit(main())
