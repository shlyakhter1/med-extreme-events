"""Build fixtures/reference/ct_legacy_county_crosswalk.csv.

Connecticut replaced its 8 counties with 9 planning regions in 2022. VetPop, PLACES and the
Census 2023 boundaries use the regions (09110-09190); NWS SAME/UGC codes still use legacy
counties (09001-09015). This derives legacy county -> regions by sampling a point grid over
each legacy county polygon (Census 2021 1:5m boundaries) and looking up the current county
of each sample; regions holding at least ``MIN_SHARE`` of a county's samples are kept.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

import httpx
import shapefile

from xevents.geography.counties import CountyIndex, _point_in_polygon

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "fixtures" / "reference" / "ct_legacy_county_crosswalk.csv"
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
URL = "https://www2.census.gov/geo/tiger/GENZ2021/shp/cb_2021_us_county_5m.zip"
GRID = 40
MIN_SHARE = 0.03


def legacy_ct(zip_bytes: bytes) -> list[tuple[str, str, list[list[list[tuple[float, float]]]]]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        stem = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(stem + ".shp")),
            dbf=io.BytesIO(zf.read(stem + ".dbf")),
            shx=io.BytesIO(zf.read(stem + ".shx")),
        )
        out = []
        for sr in reader.iterShapeRecords():
            rec = sr.record.as_dict()
            if rec["STATEFP"] != "09":
                continue
            geom = sr.shape.__geo_interface__
            raw = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            polys = [[[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in raw]
            out.append((rec["GEOID"], rec["NAME"], polys))
    return sorted(out)


def sample_regions(
    polys: list[list[list[tuple[float, float]]]], counties: CountyIndex
) -> Counter[str]:
    pts = [pt for poly in polys for ring in poly for pt in ring]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    hits: Counter[str] = Counter()
    for i in range(GRID):
        for j in range(GRID):
            x = x0 + (x1 - x0) * (i + 0.5) / GRID
            y = y0 + (y1 - y0) * (j + 0.5) / GRID
            if any(_point_in_polygon(x, y, poly) for poly in polys):
                hit = counties.lookup(x, y)
                if hit is not None:
                    hits[hit.geoid] += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None)
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / URL.rsplit("/", 1)[-1]
    if args.zip:
        data = args.zip.read_bytes()
    elif raw.exists():
        data = raw.read_bytes()
    else:
        with httpx.Client(
            timeout=120, headers={"User-Agent": "med-extreme-events fixture builder"}
        ) as c:
            r = c.get(URL)
            r.raise_for_status()
            data = r.content
    counties = CountyIndex.load()
    rows = []
    for geoid, name, polys in legacy_ct(data):
        hits = sample_regions(polys, counties)
        total = sum(hits.values())
        for region, n in sorted(hits.items()):
            if total and n / total >= MIN_SHARE:
                rows.append((geoid, name, region, f"{n / total:.3f}"))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["legacy_county_fips", "legacy_county", "county_fips", "area_share"])
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} legacy→region rows; source {URL})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
