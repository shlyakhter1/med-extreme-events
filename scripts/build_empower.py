"""Build fixtures/reference/empower_county.csv and empower_zip.csv from the HHS emPOWER
public REST service.

Source: ``HHS_emPOWER_REST_Service_Public`` (ArcGIS Online, owner DHHS_gissupport;
also mirrored at geohealth.hhs.gov/dataaccess). De-identified monthly counts of Medicare
(FFS + Advantage) beneficiaries who rely on electricity-dependent durable medical equipment,
by ZIP (layer 1) and county (layer 2). Layer ids and field names are pinned below and the
script fails loudly if the portal renames them. Small cells (1–10) are masked to 11 upstream.

The data vintage is the service's ``dataLastEditDate``; it and the retrieval date go into
the ``#`` header line of each CSV (loaders skip it). Refresh manually, monthly.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
REF = REPO_ROOT / "fixtures" / "reference"
RAW = REF / "raw"
SERVICE = (
    "https://services2.arcgis.com/ZQ4jTQn6k7VPXEwO/arcgis/rest/services/"
    "HHS_emPOWER_REST_Service_Public/FeatureServer"
)
COUNTY_LAYER = 2  # "Electricity Dependent DME – ALL – CountyLevel"
ZIP_LAYER = 1  # "Electricity Dependent DME – ALL – ZipLevel"
PAGE = 2000
# emPOWER field → our column. Every field must be present or the build stops.
MEASURES = {
    "Medicare_Benes": "medicare_benes",
    "Power_Dependent_Devices_DME": "power_dependent_dme",
    "Facility_ESRD_Dialysis_Any_DME": "esrd_dialysis_dme",
    "O2_Services_Any_DME": "o2_dme",
    "Home_Health_Services_Any_DME": "home_health_dme",
    "AtHome_Hospice_Any_DME": "hospice_dme",
    "Any_Healthcare_Srvc_Any_DME": "any_healthcare_dme",
}
COUNTY_KEYS = {"FIPS_Code": "county_fips", "State": "state", "County": "county"}
ZIP_KEYS = {"Zip_Code": "zip", "FIPS_Code": "county_fips", "STATE": "state"}


def layer_info(client: httpx.Client, layer: int) -> dict[str, Any]:
    r = client.get(f"{SERVICE}/{layer}", params={"f": "json"})
    r.raise_for_status()
    doc: dict[str, Any] = r.json()
    if "error" in doc:
        raise SystemExit(f"emPOWER layer {layer}: {doc['error']}")
    names = {f["name"] for f in doc.get("fields", [])}
    missing = [f for f in MEASURES if f not in names]
    if missing:
        raise SystemExit(f"emPOWER layer {layer} ({doc.get('name')}) lacks fields {missing}")
    return doc


def fetch_layer(
    client: httpx.Client, layer: int, raw_path: Path, keys: dict[str, str], *, refresh: bool
) -> list[dict[str, Any]]:
    if raw_path.exists() and not refresh:
        return list(json.loads(raw_path.read_text(encoding="utf-8"))["features"])
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        r = client.get(
            f"{SERVICE}/{layer}/query",
            params={
                "where": "1=1",
                "outFields": ",".join([*MEASURES, *keys]),
                "returnGeometry": "false",
                "resultOffset": str(offset),
                "resultRecordCount": str(PAGE),
                "orderByFields": "OBJECTID",
                "f": "json",
            },
        )
        r.raise_for_status()
        doc = r.json()
        if "error" in doc:
            raise SystemExit(f"emPOWER layer {layer} query: {doc['error']}")
        page = doc.get("features", [])
        features.extend(page)
        if not doc.get("exceededTransferLimit") or not page:
            break
        offset += len(page)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({"features": features}), encoding="utf-8")
    return features


def rows_from(features: list[dict[str, Any]], keys: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for feat in features:
        a = feat["attributes"]
        row: dict[str, Any] = {out: str(a.get(src) or "").strip() for src, out in keys.items()}
        if "county_fips" in row:
            row["county_fips"] = row["county_fips"].zfill(5)
            if not row["county_fips"].isdigit() or row["county_fips"] == "00000":
                continue  # territory aggregates without a county FIPS
        if "zip" in row:
            row["zip"] = row["zip"].zfill(5)
        for src, out in MEASURES.items():
            v = a.get(src)
            row[out] = int(v) if v is not None else ""
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str], header: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# {header}\n")
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in sorted(rows, key=lambda r: tuple(r[c] for c in columns[:2])):
            w.writerow(r)


def main() -> int:
    refresh = "--refresh" in sys.argv
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        info = layer_info(client, COUNTY_LAYER)
        layer_info(client, ZIP_LAYER)
        edited = info.get("editingInfo", {}).get("dataLastEditDate")
        vintage = (
            datetime.fromtimestamp(edited / 1000, tz=UTC).strftime("%Y-%m-%d") if edited else "?"
        )
        retrieved = datetime.now(UTC).strftime("%Y-%m-%d")
        header = (
            f"HHS emPOWER public REST service ({SERVICE}), data vintage {vintage} "
            f"(service dataLastEditDate), retrieved {retrieved}; Medicare FFS+MA beneficiaries, "
            "de-identified, cells 1-10 masked to 11"
        )
        county = rows_from(
            fetch_layer(
                client, COUNTY_LAYER, RAW / "empower_county.json", COUNTY_KEYS, refresh=refresh
            ),
            COUNTY_KEYS,
        )
        zips = rows_from(
            fetch_layer(client, ZIP_LAYER, RAW / "empower_zip.json", ZIP_KEYS, refresh=refresh),
            ZIP_KEYS,
        )
    write_csv(
        REF / "empower_county.csv",
        county,
        [*COUNTY_KEYS.values(), *MEASURES.values()],
        f"{header}; layer {COUNTY_LAYER} county",
    )
    write_csv(
        REF / "empower_zip.csv",
        zips,
        [*ZIP_KEYS.values(), *MEASURES.values()],
        f"{header}; layer {ZIP_LAYER} ZIP",
    )
    print(
        f"wrote empower_county.csv ({len(county)} counties) and empower_zip.csv "
        f"({len(zips)} ZIPs); vintage {vintage}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
