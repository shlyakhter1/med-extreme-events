"""Run the matching engine over the event store and persist action items.

``--scenario NAME`` (or ``EVENT_MODE=replay``, all scenarios): match that scenario's events
"as of" the end of its window (every item the replay would ever issue). Live mode matches
the live events (scenario NULL) as of now and auto-expires stale items. Re-runs upsert by
natural key: content refreshes, delivery/acknowledgement progress is kept, and a strengthened
alert supersedes its weaker sibling.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

from xevents.cards import load_cards
from xevents.denominators import PanelEstimator, ReferenceTables
from xevents.engine import match
from xevents.geography.counties import CountyIndex
from xevents.models import Card, Estimate
from xevents.profiles import PROFILES_DIR, load_profile
from xevents.providers.replay import list_scenarios
from xevents.store import (
    catchment_map,
    expire_action_items,
    init_db,
    list_events,
    list_facilities,
    make_engine,
    station_map,
    upsert_action_items,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["replay", "live"], default=os.environ.get("EVENT_MODE", "replay")
    )
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    engine = make_engine(args.database_url)
    init_db(engine)
    profile = load_profile(PROFILES_DIR / "va.yaml")
    cards = load_cards()
    facilities = list_facilities(engine)
    if not facilities:
        print("no facilities loaded — run `make load` first", file=sys.stderr)
        return 1
    tables = ReferenceTables.load(
        profile.catchment.projection_year, county_ids=CountyIndex.load().ids()
    )
    estimator = PanelEstimator(profile, tables, catchment_map(engine), station_map(engine))

    def panels(facility_id: str, card: Card) -> Estimate | None:
        return estimator.card_panel(facility_id, card)

    now = datetime.now(UTC)
    scenarios: list[str | None]
    if args.mode == "replay":
        scenarios = [args.scenario] if args.scenario else list(list_scenarios())
    else:
        scenarios = [None]
    for scenario in scenarios:
        events = (
            list_events(engine, scenario=scenario)
            if scenario
            else [e for e in list_events(engine) if e.scenario is None]
        )
        result = match(events, cards, facilities, profile, panels, now=now)
        counts = upsert_action_items(engine, result.items)
        matched = sum(1 for t in result.log if t.matched)
        label = scenario or "live"
        superseded = sum(1 for i in result.items if i.superseded_by)
        print(
            f"{label}: {len(events)} events, {matched} trigger matches, {len(result.items)} items "
            f"({superseded} superseded) → {counts}"
        )
    if args.mode == "live":
        print(f"expired: {expire_action_items(engine, now)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
