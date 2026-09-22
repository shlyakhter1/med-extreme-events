"""Build fixtures/reference/places_county.csv from CDC PLACES county estimates.

Source: CDC PLACES, County Data (GIS Friendly Format), 2025 release, Socrata id
``i46a-9kgh`` on data.cdc.gov (see ../nyc2026-dataset skill ``search-cdc-places``).
Model-based crude prevalence (%) among adults >= 18 for the measures the profiles use.
Note: PLACES dropped the CKD (``kidney``) measure after the 2023 release; it is not here.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "fixtures" / "reference" / "places_county.csv"
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
DATASET = "i46a-9kgh"
RELEASE = "2025"
URL = f"https://data.cdc.gov/resource/{DATASET}.json"
MEASURES = [
    "copd",
    "casthma",
    "chd",
    "diabetes",
    "depression",
    "mhlth",
    "bphigh",
    "obesity",
    "stroke",
    "disability",
]
COLUMNS = ["stateabbr", "countyname", "countyfips", "totalpopulation", "totalpop18plus"] + [
    f"{m}_crudeprev" for m in MEASURES
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None, help="use a saved raw JSON response")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"places_county_{RELEASE}_{DATASET}.json"
    if args.file:
        raw_path.write_bytes(args.file.read_bytes())
    elif not raw_path.exists():
        params = {"$select": ",".join(COLUMNS), "$limit": "5000"}
        with httpx.Client(
            timeout=120, headers={"User-Agent": "med-extreme-events fixture builder"}
        ) as c:
            r = c.get(URL, params=params)
            r.raise_for_status()
            raw_path.write_bytes(r.content)
    rows = json.loads(raw_path.read_text(encoding="utf-8"))
    if not rows:
        raise SystemExit("PLACES payload is empty — not overwriting the committed table")
    # Build every output row before touching the file: a renamed upstream field must fail
    # here, not leave a header-only CSV over the committed one.
    out_rows = [
        [
            r["countyfips"],
            r["stateabbr"],
            r["countyname"],
            r.get("totalpopulation", ""),
            r.get("totalpop18plus", ""),
        ]
        + [r.get(f"{m}_crudeprev", "") for m in MEASURES]
        for r in sorted(rows, key=lambda r: r["countyfips"])
    ]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["county_fips", "state", "county", "population", "population_18plus", *MEASURES])
        w.writerows(out_rows)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    print(
        f"wrote {OUT} ({len(rows)} counties, PLACES {RELEASE} release {DATASET}, retrieved {stamp})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
