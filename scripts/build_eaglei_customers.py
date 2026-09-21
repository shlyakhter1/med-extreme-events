"""Build fixtures/reference/eaglei_customers.csv (and eaglei_state_coverage.csv).

Source: ORNL EAGLE-I figshare deposit (doi:10.6084/m9.figshare.24237376), supplementary
files ``MCC.csv`` — modeled electric customers per county as of 2022 (Moehl et al.; the
customer denominator described with Brelsford et al. 2024, Sci Data,
doi:10.1038/s41597-024-03095-5) — and ``coverage_history.csv`` (share of each state's
customers covered by EAGLE-I, 2018–2022). Raw copies are kept under ``raw/`` (both under
50 KB) and re-downloaded when missing.
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
REF = REPO_ROOT / "fixtures" / "reference"
RAW = REF / "raw"
OUT_CUSTOMERS = REF / "eaglei_customers.csv"
OUT_COVERAGE = REF / "eaglei_state_coverage.csv"
FILES = {
    "eaglei_MCC.csv": "https://ndownloader.figshare.com/files/42547708",
    "eaglei_coverage_history.csv": "https://ndownloader.figshare.com/files/42547714",
}


def fetch(name: str) -> Path:
    dest = RAW / name
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as c:
        r = c.get(FILES[name])
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def build_customers(src: Path) -> int:
    rows = []
    with src.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            raw = r["County_FIPS"].strip()
            if not raw.isdigit():  # the file ends with a 'Grand Total' row
                continue
            fips = raw.zfill(5)
            if len(fips) != 5:
                raise SystemExit(f"unexpected County_FIPS {raw!r}")
            rows.append((fips, int(float(r["Customers"]))))
    rows.sort()
    with OUT_CUSTOMERS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["county_fips", "customers"])
        w.writerows(rows)
    return len(rows)


def build_coverage(src: Path) -> int:
    latest: dict[str, tuple[datetime, dict[str, str]]] = {}
    with src.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            when = datetime.strptime(r["year"], "%m/%d/%y").replace(tzinfo=UTC)
            cur = latest.get(r["state"])
            if cur is None or when > cur[0]:
                latest[r["state"]] = (when, r)
    with OUT_COVERAGE.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["state", "vintage", "total_customers", "pct_covered"])
        for state in sorted(latest):
            when, r = latest[state]
            w.writerow(
                [state, when.strftime("%Y-%m-%d"), r["total_customers"], r["max_pct_covered"]]
            )
    return len(latest)


def main() -> int:
    n = build_customers(fetch("eaglei_MCC.csv"))
    m = build_coverage(fetch("eaglei_coverage_history.csv"))
    print(f"wrote {OUT_CUSTOMERS} ({n} counties) and {OUT_COVERAGE} ({m} states)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
