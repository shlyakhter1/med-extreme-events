"""Build fixtures/reference/counties.geojson from Census cartographic boundary files.

Source: Census Bureau cartographic boundary shapefile, counties, 1:5,000,000 (the 1:20m file
omits Guam and the other Pacific/Caribbean territories; 1:5m includes them and
is accurate enough for facility points). The raw zip is kept under ``fixtures/reference/raw/``.

Output: GeoJSON FeatureCollection with properties ``geoid`` (5-digit county FIPS),
``name``, ``state_fips``, ``state`` (USPS), and a ``bbox`` per feature for fast prefilter.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import shapefile

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
OUT = REPO_ROOT / "fixtures" / "reference" / "counties.geojson"
VINTAGE = "2023"
URL = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/cb_{VINTAGE}_us_county_5m.zip"


def convert(zip_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        stem = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(stem + ".shp")),
            dbf=io.BytesIO(zf.read(stem + ".dbf")),
            shx=io.BytesIO(zf.read(stem + ".shx")),
        )
        features: list[dict[str, Any]] = []
        for sr in reader.iterShapeRecords():
            rec = sr.record.as_dict()
            geom: dict[str, Any] = sr.shape.__geo_interface__
            xs = [pt[0] for ring in _rings(geom) for pt in ring]
            ys = [pt[1] for ring in _rings(geom) for pt in ring]
            features.append(
                {
                    "type": "Feature",
                    "id": rec["GEOID"],
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "geometry": {
                        "type": geom["type"],
                        "coordinates": _round(geom["coordinates"]),
                    },
                    "properties": {
                        "geoid": rec["GEOID"],
                        "name": rec["NAME"],
                        "state_fips": rec["STATEFP"],
                        "state": rec["STUSPS"],
                    },
                }
            )
    features.sort(key=lambda f: str(f["id"]))
    return {"type": "FeatureCollection", "features": features}


def _rings(geom: dict[str, Any]) -> list[list[tuple[float, float]]]:
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        return [list(r) for r in coords]
    return [list(r) for poly in coords for r in poly]


def _round(coords: Any, ndigits: int = 5) -> Any:
    if isinstance(coords, (list, tuple)):
        if coords and isinstance(coords[0], (int, float)):
            return [round(float(c), ndigits) for c in coords]
        return [_round(c, ndigits) for c in coords]
    return coords


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="use a local copy of the zip")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / URL.rsplit("/", 1)[-1]
    if args.zip:
        data = args.zip.read_bytes()
    else:
        with httpx.Client(
            timeout=120, headers={"User-Agent": "med-extreme-events fixture builder"}
        ) as c:
            r = c.get(URL)
            r.raise_for_status()
            data = r.content
    raw_path.write_bytes(data)
    doc = convert(data)
    doc["provenance"] = {
        "source": URL,
        "retrieved": datetime.now(UTC).strftime("%Y-%m-%d"),
        "count": len(doc["features"]),
        "builder": "scripts/build_county_boundaries.py",
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(doc['features'])} counties, {OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
