"""UGC → county FIPS resolution for NWS products.

County UGCs (``SSCnnn``) map directly via the state FIPS table; zone UGCs (``SSZnnn``) map
through ``fixtures/reference/nws_zone_county.csv`` (NWS zone-county correlation file).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = REPO_ROOT / "fixtures" / "reference" / "nws_zone_county.csv"

STATE_FIPS: dict[str, str] = {
    "AL": "01",
    "AK": "02",
    "AZ": "04",
    "AR": "05",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DE": "10",
    "DC": "11",
    "FL": "12",
    "GA": "13",
    "HI": "15",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "IA": "19",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "ME": "23",
    "MD": "24",
    "MA": "25",
    "MI": "26",
    "MN": "27",
    "MS": "28",
    "MO": "29",
    "MT": "30",
    "NE": "31",
    "NV": "32",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "NC": "37",
    "ND": "38",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "UT": "49",
    "VT": "50",
    "VA": "51",
    "WA": "53",
    "WV": "54",
    "WI": "55",
    "WY": "56",
    "AS": "60",
    "GU": "66",
    "MP": "69",
    "PR": "72",
    "VI": "78",
}


class UgcResolver:
    def __init__(self, zone_to_counties: dict[str, list[str]]) -> None:
        self._zones = zone_to_counties

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> UgcResolver:
        zones: dict[str, list[str]] = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                zones[r["ugc_zone"]].append(r["county_fips"])
        return cls(dict(zones))

    @classmethod
    def empty(cls) -> UgcResolver:
        return cls({})

    def __len__(self) -> int:
        return len(self._zones)

    def zone_map(self) -> dict[str, list[str]]:
        return dict(self._zones)

    def counties(self, ugc: str) -> list[str]:
        """County FIPS for one UGC code; empty if unknown."""
        state, kind, num = ugc[:2], ugc[2], ugc[3:]
        if kind == "C":
            fips = STATE_FIPS.get(state)
            return [fips + num] if fips and num.isdigit() else []
        return list(self._zones.get(ugc, []))

    def resolve(self, ugcs: list[str], same: list[str] | None = None) -> tuple[list[str], str]:
        """Counties for a set of UGCs plus optional CAP SAME codes. Returns (fips, note)."""
        found: set[str] = set()
        unresolved: list[str] = []
        for code in same or []:
            digits = code.strip()
            if len(digits) == 6 and digits.isdigit() and digits[0] == "0":
                found.add(digits[1:])
        for ugc in ugcs:
            hits = self.counties(ugc)
            if hits:
                found.update(hits)
            elif ugc[2] == "Z":
                unresolved.append(ugc)
        note = (
            "counties from SAME/county UGC"
            if not unresolved
            else (f"zones without county mapping: {unresolved}")
        )
        if any(u[2] == "Z" for u in ugcs) and not unresolved:
            note = "counties via NWS zone-county correlation"
        return sorted(found), note
