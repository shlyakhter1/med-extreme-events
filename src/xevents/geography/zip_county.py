"""ZIP → county (dominant share) crosswalk, loaded from ``fixtures/reference/zip_county.csv``.

Built by ``scripts/build_zip_county.py`` from HUD USPS (address shares) when a token is
available, else from the Census 2020 ZCTA↔county relationship file (land-area shares).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = REPO_ROOT / "fixtures" / "reference" / "zip_county.csv"


@dataclass(frozen=True)
class CountyMatch:
    county_fips: str
    share: float
    source: str


class ZipCountyCrosswalk:
    def __init__(self, rows: dict[str, CountyMatch]) -> None:
        self._rows = rows

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> ZipCountyCrosswalk:
        rows: dict[str, CountyMatch] = {}
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["zip"]] = CountyMatch(r["county_fips"], float(r["share"]), r["source"])
        if not rows:
            raise ValueError(f"{path}: empty crosswalk")
        return cls(rows)

    def __len__(self) -> int:
        return len(self._rows)

    def lookup(self, zip5: str | None) -> CountyMatch | None:
        if zip5 is None:
            return None
        return self._rows.get(zip5)
