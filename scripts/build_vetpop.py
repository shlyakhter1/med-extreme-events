"""Build fixtures/reference/vetpop_county.csv from VA VetPop2023 county projections.

Source: VA NCVAS VetPop2023, Table 9L "County-level veteran population by state, age group,
sex, 2023-2053" (all ages, both sexes), workbook ``9L_VetPop2023_County_NCVAS.xlsx`` from
https://www.va.gov/vetdata/veteran_population.asp. Output keeps the 9/30 projection for
each year 2023-2030 as ``veterans_<year>``. The 16 MB workbook is cached under ``raw/``
but git-ignored; the builder re-downloads it when missing.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "fixtures" / "reference" / "vetpop_county.csv"
RAW_DIR = REPO_ROOT / "fixtures" / "reference" / "raw"
URL = (
    "https://www.va.gov/VETDATA/docs/Demographics/New_Vetpop_Model/9L_VetPop2023_County_NCVAS.xlsx"
)
YEARS = list(range(2023, 2031))


def convert(xlsx_path: Path) -> list[list[str]]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(values_only=True)
    header: tuple[object, ...] | None = None
    for row in rows_iter:
        if row and row[0] == "FIPS":
            header = row
            break
    if header is None:
        raise SystemExit("VetPop header row (FIPS, County, dates) not found")
    col_for_year = {}
    for idx, cell in enumerate(header):
        if isinstance(cell, str) and cell.startswith("9/30/"):
            col_for_year[int(cell[5:])] = idx
        elif hasattr(cell, "year"):
            col_for_year[cell.year] = idx
    out = []
    for row in rows_iter:
        fips = row[0]
        if fips is None or not str(fips).strip():
            continue
        fips_s = str(fips).split(".")[0].zfill(5)
        if not fips_s.isdigit() or len(fips_s) != 5:
            continue
        values = []
        for y in YEARS:
            v = row[col_for_year[y]] if y in col_for_year else None
            values.append(str(round(float(v))) if isinstance(v, (int, float)) else "")
        out.append([fips_s, str(row[1] or "").strip(), *values])
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=None, help="use a local copy of the workbook")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / URL.rsplit("/", 1)[-1]
    if args.file:
        raw_path.write_bytes(args.file.read_bytes())
    elif not raw_path.exists():
        with httpx.Client(
            timeout=300,
            headers={"User-Agent": "Mozilla/5.0 med-extreme-events"},
            follow_redirects=True,
        ) as c:
            r = c.get(URL)
            r.raise_for_status()
            raw_path.write_bytes(r.content)
    rows = convert(raw_path)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["county_fips", "county", *[f"veterans_{y}" for y in YEARS]])
        w.writerows(rows)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    print(f"wrote {OUT} ({len(rows)} counties, VetPop2023 Table 9L, retrieved {stamp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
