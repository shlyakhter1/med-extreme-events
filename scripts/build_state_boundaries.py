"""Build fixtures/reference/states.geojson from Census cartographic boundary files.

Source: Census Bureau cartographic boundary shapefile, states, 1:5,000,000, vintage 2023 —
the same scale and vintage as ``counties.geojson``, so state lines sit exactly on county
edges. The raw zip is kept under ``fixtures/reference/raw/``.

Output: GeoJSON FeatureCollection, one feature per state/territory, properties ``state_fips``,
``state`` (USPS) and ``name``. Coordinates are rounded to 4 decimals (~11 m) and consecutive
duplicate points dropped: the layer is an outline overlay, not a join key.
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
OUT = REPO_ROOT / "fixtures" / "reference" / "states.geojson"
VINTAGE = "2023"
URL = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/cb_{VINTAGE}_us_state_5m.zip"
NDIGITS = 4


def _ring(points: Any) -> list[list[float]]:
    out: list[list[float]] = []
    for x, y in points:
        pt = [round(float(x), NDIGITS), round(float(y), NDIGITS)]
        if not out or out[-1] != pt:
            out.append(pt)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out


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
            if geom["type"] == "Polygon":
                coords: Any = [
                    r for r in (_ring(ring) for ring in geom["coordinates"]) if len(r) >= 4
                ]
            else:
                coords = [
                    [r for r in (_ring(ring) for ring in poly) if len(r) >= 4]
                    for poly in geom["coordinates"]
                ]
                coords = [p for p in coords if p]
            features.append(
                {
                    "type": "Feature",
                    "id": rec["STATEFP"],
                    "geometry": {"type": geom["type"], "coordinates": coords},
                    "properties": {
                        "state_fips": rec["STATEFP"],
                        "state": rec["STUSPS"],
                        "name": rec["NAME"],
                    },
                }
            )
    features.sort(key=lambda f: str(f["id"]))
    return {"type": "FeatureCollection", "features": features}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="use a local copy of the zip")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / URL.rsplit("/", 1)[-1]
    if args.zip:
        data = args.zip.read_bytes()
    elif raw_path.exists():
        data = raw_path.read_bytes()
    else:
        with httpx.Client(
            timeout=120, headers={"User-Agent": "med-extreme-events fixture builder"}
        ) as c:
            r = c.get(URL)
            r.raise_for_status()
            data = r.content
        raw_path.write_bytes(data)
    doc = convert(data)
    if not doc["features"]:
        raise SystemExit("no state features — not overwriting the committed file")
    doc["provenance"] = {
        "source": URL,
        "retrieved": datetime.now(UTC).strftime("%Y-%m-%d"),
        "count": len(doc["features"]),
        "builder": "scripts/build_state_boundaries.py",
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(doc['features'])} states, {OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
