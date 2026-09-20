"""Build fixtures/reference/zip_county.csv (ZIP → dominant county) from public sources.

Preferred source: HUD USPS ZIP-County crosswalk (address-share ratios). It needs a free
HUD API token (``HUD_API_TOKEN``, https://www.huduser.gov/portal/dataset/uspszip-api.html).
Fallback (no token): Census 2020 ZCTA↔county relationship file, using land-area share of
each ZCTA part as the dominance measure. ZCTAs approximate ZIPs; the output records which
source produced each row.

Output columns: zip, county_fips, share, source
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "fixtures" / "reference" / "zip_county.csv"
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
CENSUS_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_county20_natl.txt"
)
HUD_URL = "https://www.huduser.gov/hudapi/public/usps?type=2&query=all"


def from_census(text: str) -> dict[str, tuple[str, float]]:
    parts: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        zcta, county = row["GEOID_ZCTA5_20"], row["GEOID_COUNTY_20"]
        if not zcta or not county:
            continue
        parts[zcta].append((county, int(row["AREALAND_PART"] or 0)))
    out: dict[str, tuple[str, float]] = {}
    for zcta, lst in parts.items():
        total = sum(a for _, a in lst)
        county, area = max(lst, key=lambda t: t[1])
        out[zcta] = (county, area / total if total else 1.0 / len(lst))
    return out


def from_hud(payload: dict[str, object]) -> dict[str, tuple[str, float]]:
    data = payload.get("data")
    results = data.get("results", []) if isinstance(data, dict) else []
    best: dict[str, tuple[str, float]] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        zip_code, county = str(r["zip"]), str(r["geoid"])
        share = float(r.get("tot_ratio", 0.0))
        if zip_code not in best or share > best[zip_code][1]:
            best[zip_code] = (county, share)
    return best


def write(rows: dict[str, tuple[str, float]], source: str) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zip", "county_fips", "share", "source"])
        for zip_code in sorted(rows):
            county, share = rows[zip_code]
            w.writerow([zip_code, county, f"{share:.4f}", source])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["auto", "hud", "census"], default="auto")
    args = parser.parse_args()
    token = os.environ.get("HUD_API_TOKEN")
    use_hud = args.source == "hud" or (args.source == "auto" and token)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    with httpx.Client(
        timeout=120, headers={"User-Agent": "med-extreme-events fixture builder"}
    ) as c:
        if use_hud:
            if not token:
                print("HUD_API_TOKEN is not set", file=sys.stderr)
                return 1
            r = c.get(HUD_URL, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            (RAW_DIR / "hud_usps_zip_county.json").write_bytes(r.content)
            rows, source = from_hud(r.json()), f"hud_usps_type2 retrieved {stamp}"
        else:
            r = c.get(CENSUS_URL)
            r.raise_for_status()
            text = r.content.decode("utf-8-sig")
            (RAW_DIR / "tab20_zcta520_county20_natl.txt").write_text(text, encoding="utf-8")
            rows, source = from_census(text), f"census_rel2020_zcta_county retrieved {stamp}"
    write(rows, source)
    print(f"wrote {OUT} ({len(rows)} rows, source={source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
