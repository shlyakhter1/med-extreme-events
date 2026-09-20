"""Build fixtures/reference/nws_zone_county.csv from the NWS zone-county correlation file.

Source: https://www.weather.gov/gis/ZoneCounty (pipe-delimited ``bpDDmmmYY.dbx``; columns
STATE|ZONE|CWA|NAME|STATE_ZONE|COUNTY|FIPS|TIME_ZONE|FE_AREA|LAT|LON). Maps public forecast
zones (UGC ``SSZnnn``) to the counties they cover. Needed because many NWS products (heat,
air quality) are issued by zone, not county.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "fixtures" / "reference" / "nws_zone_county.csv"
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
INDEX_URL = "https://www.weather.gov/gis/ZoneCounty"
BASE = "https://www.weather.gov/source/gis/Shapefiles/County/"


def latest_file(index_html: str) -> str:
    names = set(re.findall(r"Shapefiles/County/(bp\d{2}[a-z]{2}\d{2}\.dbx)", index_html))
    if not names:
        raise SystemExit("no bp*.dbx links found on the ZoneCounty page")

    def key(n: str) -> tuple[int, int, int]:
        m = re.match(r"bp(\d{2})([a-z]{2})(\d{2})\.dbx", n)
        assert m
        months = ["ja", "fe", "mr", "ap", "my", "jn", "jl", "au", "se", "oc", "nv", "de"]
        return (int(m.group(3)), months.index(m.group(2)), int(m.group(1)))

    latest: str = max(names, key=key)
    return latest


def convert(text: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 7 or not parts[6].strip().isdigit():
            continue
        state, zone, county_name, fips = parts[0], parts[1], parts[5], parts[6].zfill(5)
        rows.append((f"{state}Z{zone.zfill(3)}", fips, county_name, state))
    return sorted(set(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None, help="use a local .dbx copy")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=60,
        headers={"User-Agent": "med-extreme-events fixture builder"},
        follow_redirects=True,
    ) as c:
        if args.file:
            name, text = args.file.name, args.file.read_text(encoding="latin-1")
        else:
            name = latest_file(c.get(INDEX_URL).text)
            r = c.get(BASE + name)
            r.raise_for_status()
            text = r.content.decode("latin-1")
    (RAW_DIR / name).write_text(text, encoding="latin-1")
    rows = convert(text)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ugc_zone", "county_fips", "county_name", "state"])
        w.writerows(rows)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"wrote {OUT} ({len(rows)} zone→county rows from {name}, retrieved {stamp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
