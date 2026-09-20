"""Load cached reference data into the database: facilities + county/VISN attribution.

Reads ``fixtures/reference/facilities.geojson``, ``counties.geojson`` and ``zip_county.csv``,
attributes each facility (point-in-polygon, then ZIP fallback), upserts into ``DATABASE_URL``
(SQLite fallback), and reports anything unresolved.
Exit status 1 if any health facility inside US county coverage lacks a county or VISN (M1
"done when"). Facilities outside coverage (e.g. the Manila VA Clinic, state ``PH``) are
reported as excluded, not as failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xevents.geography import CountyIndex, ZipCountyCrosswalk, attribute_facilities
from xevents.providers.va_facilities import from_geojson
from xevents.store import init_db, make_engine, upsert_facilities

REPO_ROOT = Path(__file__).resolve().parents[1]
FACILITIES = REPO_ROOT / "fixtures" / "reference" / "facilities.geojson"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facilities", type=Path, default=FACILITIES)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    if not args.facilities.exists():
        print(
            f"{args.facilities} missing — run `make reference` (needs VA_FACILITIES_API_KEY)",
            file=sys.stderr,
        )
        return 1
    facilities = from_geojson(json.loads(args.facilities.read_text(encoding="utf-8")))
    counties = CountyIndex.load()
    report = attribute_facilities(facilities, ZipCountyCrosswalk.load(), counties)
    by_id = {f.id: f for f in report.facilities}
    outside = [i for i in report.unresolved_county if by_id[i].state not in counties.states]
    failures = [i for i in report.unresolved_county if i not in outside]
    engine = make_engine(args.database_url)
    init_db(engine)
    n = upsert_facilities(engine, report.facilities)
    print(
        f"loaded {n} facilities into {engine.url}; county attribution by method: {report.by_method}"
    )
    if outside:
        print(f"outside US county coverage, excluded from matching: {outside}")
    if failures:
        print(f"no county for {len(failures)}: {failures[:10]}", file=sys.stderr)
    if report.unresolved_visn:
        print(
            f"no VISN for {len(report.unresolved_visn)}: {report.unresolved_visn[:10]}",
            file=sys.stderr,
        )
    return 0 if not failures and not report.unresolved_visn else 1


if __name__ == "__main__":
    sys.exit(main())
