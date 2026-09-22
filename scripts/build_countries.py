"""Build fixtures/reference/countries.geojson: the US's neighbours as a muted basemap layer.

Source: Natural Earth 1:50m Admin 0 – Countries (public domain), naturalearthdata.com. The
raw zip is kept under ``fixtures/reference/raw/``. Only the neighbours a US map needs are kept
(Canada, Mexico, and Cuba and the Bahamas for Gulf/Atlantic hurricanes); the US itself is
drawn from the Census counties. Coordinates rounded to 2 decimals (~1 km), rings under four
points and consecutive duplicates dropped: it is a backdrop, never a join key, and carries
no data — events stay US-only.
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
OUT = REPO_ROOT / "fixtures" / "reference" / "countries.geojson"
URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
KEEP = {"CAN", "MEX", "CUB", "BHS"}
NDIGITS = 2


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
            code = rec.get("ADM0_A3") or rec.get("ISO_A3")
            if code not in KEEP:
                continue
            geom: dict[str, Any] = sr.shape.__geo_interface__
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            coords = [[r for r in (_ring(ring) for ring in poly) if len(r) >= 4] for poly in polys]
            coords = [p for p in coords if p]
            features.append(
                {
                    "type": "Feature",
                    "id": code,
                    "geometry": {"type": "MultiPolygon", "coordinates": coords},
                    "properties": {"iso_a3": code, "name": rec["NAME"]},
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
            timeout=120,
            follow_redirects=True,
            headers={"User-Agent": "med-extreme-events fixture builder"},
        ) as c:
            r = c.get(URL)
            r.raise_for_status()
            data = r.content
        raw_path.write_bytes(data)
    doc = convert(data)
    if {f["id"] for f in doc["features"]} != KEEP:
        raise SystemExit("missing countries — not overwriting the committed file")
    doc["provenance"] = {
        "source": URL,
        "license": "public domain (Natural Earth)",
        "retrieved": datetime.now(UTC).strftime("%Y-%m-%d"),
        "count": len(doc["features"]),
        "builder": "scripts/build_countries.py",
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(doc['features'])} countries, {OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
