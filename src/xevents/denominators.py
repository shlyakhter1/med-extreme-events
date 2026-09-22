"""Mode A panel sizing: veterans in a station's catchment × condition rate × class share.

Rates come from the population profile: a VA-literature multiplier when the profile gives
one (diabetes 0.25, CHF 0.05, ...) applied to the scope it was measured on (VHA users =
veterans × share), else a CDC PLACES county prevalence applied to all veterans; national
counts (dialysis) are allocated by the station's share of veterans. Every ``Estimate``
carries formula, inputs, sources and caveats for the UI's "how was this computed" popover.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from xevents.models import Card, Estimate
from xevents.profiles import Denominator, Profile

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "fixtures" / "reference"
VETPOP_PATH = REFERENCE / "vetpop_county.csv"
PLACES_PATH = REFERENCE / "places_county.csv"
EMPOWER_PATH = REFERENCE / "empower_county.csv"
EMPOWER_UNIT = "Medicare beneficiaries"
META_COLUMNS = {"county_fips", "state", "county", "population", "population_18plus"}
# VetPop reports territories as single rows; spread them over the territory's counties.
TERRITORY_ROWS = {"72000": "72", "90066": "66", "90078": "78", "90060": "60", "90069": "69"}

PLACES_CAVEAT = (
    "CDC PLACES rates are model-based estimates for adults 18+ in the general population, "
    "not veterans; treat as a planning benchmark."
)
ESTIMATE_CAVEAT = "Planning estimate (aggregate, no patient data): population × rate, not a count."
CATCHMENT_CAVEAT = (
    "Catchment = counties whose nearest anchor station (VAMC/HCC) is this one; clinics report "
    "their station's panel (Mode A approximation)."
)
MEDICARE_PROXY_CAVEAT = (
    "emPOWER, measured; Medicare proxy — not veteran-specific. Counts Medicare (FFS + Advantage) "
    "beneficiaries with electricity-dependent DME claims; shown beside the veteran estimate, "
    "never in place of it."
)
EMPOWER_MASKING_CAVEAT = "emPOWER masks small cells (1–10) to 11, so small counties read high."


def load_empower(path: Path = EMPOWER_PATH) -> tuple[dict[str, dict[str, int | None]], str]:
    """County FIPS → emPOWER measure → count, plus the vintage line from the ``#`` header."""
    header = ""
    rows: dict[str, dict[str, int | None]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        first = f.readline()
        if first.startswith("#"):
            header = first[1:].strip()
        else:
            f.seek(0)
        reader = csv.DictReader(f)
        measures = [
            c for c in (reader.fieldnames or []) if c not in {"county_fips", "state", "county"}
        ]
        for r in reader:
            rows[r["county_fips"]] = {m: (int(r[m]) if r[m] else None) for m in measures}
    return rows, header


@dataclass
class ReferenceTables:
    veterans: dict[str, int]  # county FIPS → veterans (projection year)
    places: dict[str, dict[str, float | None]]  # county FIPS → measure → crude prevalence %
    projection_year: int
    vetpop_source: str = field(default="VetPop2023 Table 9L")
    places_source: str = field(default="CDC PLACES 2025 county release")
    excluded: dict[str, int] = field(default_factory=dict)  # VetPop rows with no US county
    empower: dict[str, dict[str, int | None]] = field(default_factory=dict)  # FIPS → measure
    empower_source: str = field(default="HHS emPOWER public REST service")
    places_measures: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def load(
        cls,
        projection_year: int,
        vetpop_path: Path = VETPOP_PATH,
        places_path: Path = PLACES_PATH,
        county_ids: set[str] | None = None,
        empower_path: Path = EMPOWER_PATH,
    ) -> ReferenceTables:
        col = f"veterans_{projection_year}"
        veterans: dict[str, int] = {}
        excluded: dict[str, int] = {}
        with vetpop_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if col not in (reader.fieldnames or []):
                raise ValueError(
                    f"{vetpop_path.name} has no column {col!r} (profile projection_year "
                    f"{projection_year}); available: "
                    f"{[c for c in reader.fieldnames or [] if c.startswith('veterans_')]}"
                )
            for r in reader:
                if r.get(col):
                    veterans[r["county_fips"]] = int(r[col])
        if county_ids is not None:
            for row_fips, state_fips in TERRITORY_ROWS.items():
                n = veterans.pop(row_fips, None)
                if n is None:
                    continue
                targets = sorted(c for c in county_ids if c.startswith(state_fips))
                for i, c in enumerate(targets):  # even split, remainder to the first counties
                    veterans[c] = (
                        veterans.get(c, 0) + n // len(targets) + (1 if i < n % len(targets) else 0)
                    )
            for fips in [k for k in veterans if k not in county_ids]:
                excluded[fips] = veterans.pop(fips)
        places: dict[str, dict[str, float | None]] = {}
        with places_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            measures = [c for c in (reader.fieldnames or []) if c not in META_COLUMNS]
            for r in reader:
                places[r["county_fips"]] = {m: (float(r[m]) if r[m] else None) for m in measures}
        empower, empower_header = load_empower(empower_path)
        return cls(
            veterans=veterans,
            places=places,
            projection_year=projection_year,
            excluded=excluded,
            places_measures=frozenset(measures),
            empower=empower,
            empower_source=f"HHS emPOWER public REST service ({empower_header})"
            if empower_header
            else "HHS emPOWER public REST service",
        )

    @property
    def national_veterans(self) -> int:
        return sum(self.veterans.values())

    def national_places_rate(self, measure: str) -> float | None:
        """Veteran-weighted national mean of a PLACES measure (fallback for gaps)."""
        num = den = 0.0
        for fips, vets in self.veterans.items():
            v = (self.places.get(fips) or {}).get(measure)
            if v is not None:
                num += vets * v
                den += vets
        return num / den if den else None


class PanelEstimator:
    def __init__(
        self,
        profile: Profile,
        tables: ReferenceTables,
        catchment: dict[str, list[str]],
        stations: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self.profile = profile
        self.tables = tables
        self.catchment = catchment  # station id → county FIPS list
        self.stations = stations or {}  # facility id → (station id, method)

    def owns_panel(self, facility_id: str) -> bool:
        """True for a station: a facility with its own catchment, and so its own panel.
        Clinics inherit their station's estimate for display, but must not be issued
        action items of their own or the same estimated patients are counted twice.
        """
        return facility_id in self.catchment

    def station_for(self, facility_id: str) -> tuple[str, str]:
        if facility_id in self.catchment:
            return facility_id, "self"
        return self.stations.get(facility_id, (facility_id, "none"))

    # ------------------------------------------------------------------ building blocks

    def veterans(self, facility_id: str) -> Estimate:
        station, method = self.station_for(facility_id)
        counties = self.catchment.get(station, [])
        total = sum(self.tables.veterans.get(c, 0) for c in counties)
        caveats = [CATCHMENT_CAVEAT]
        if method not in ("self", "none"):
            caveats.append(f"Sized at parent station {station} (matched by {method}).")
        return Estimate(
            label="Veterans in catchment",
            value=float(total),
            formula=(
                f"Σ VetPop {self.tables.projection_year} veterans over "
                f"{len(counties)} catchment counties of station {station}"
            ),
            inputs={
                "facility_id": facility_id,
                "station_id": station,
                "counties": ",".join(counties),
                "projection_year": self.tables.projection_year,
            },
            sources=[self.tables.vetpop_source, "profile catchment rule: nearest anchor station"],
            caveats=caveats,
        )

    def _scoped_population(self, facility_id: str, den: Denominator) -> Estimate:
        vets = self.veterans(facility_id)
        if den.scope == "veterans":
            return vets
        scope = self.profile.scopes[den.scope]
        return Estimate(
            label=f"{den.scope} in catchment",
            value=vets.value * scope.share_of_veterans,
            formula=(
                f"veterans_in_catchment × share_of_veterans[{den.scope}] = "
                f"{vets.value:.0f} × {scope.share_of_veterans}"
            ),
            inputs={
                "veterans_in_catchment": vets.value,
                "share_of_veterans": scope.share_of_veterans,
            },
            sources=[scope.source],
            caveats=[c for c in [scope.note] if c],
            components=[vets],
        )

    def empower_dme(self, facility_id: str, key: str = "empower_dme") -> Estimate:
        """Measured exposure layer: emPOWER electricity-dependent-DME Medicare beneficiaries
        summed over the station's catchment counties. Unit is Medicare beneficiaries, never
        veterans; the label says so, and it never replaces a condition panel."""
        den = self.profile.denominators[key]
        measure = den.empower_measure or ""
        station, method = self.station_for(facility_id)
        counties = self.catchment.get(station, [])
        total = 0
        missing = 0
        for c in counties:
            v = (self.tables.empower.get(c) or {}).get(measure)
            if v is None:
                missing += 1
                continue
            total += v
        caveats = [MEDICARE_PROXY_CAVEAT, EMPOWER_MASKING_CAVEAT, den.basis, CATCHMENT_CAVEAT]
        if den.note:
            caveats.append(den.note)
        if missing:
            caveats.append(f"{missing} of {len(counties)} catchment counties have no emPOWER row.")
        if method not in ("self", "none"):
            caveats.append(f"Sized at parent station {station} (matched by {method}).")
        return Estimate(
            label=(
                "Electricity-dependent DME Medicare beneficiaries in catchment (emPOWER, measured)"
            ),
            value=float(total),
            unit=EMPOWER_UNIT,
            formula=(
                f"Σ emPOWER {measure}(c) over {len(counties)} catchment counties of "
                f"station {station}"
            ),
            inputs={
                "facility_id": facility_id,
                "station_id": station,
                "measure": measure,
                "counties": len(counties),
            },
            sources=[den.source, self.tables.empower_source],
            caveats=caveats,
        )

    def condition_panel(self, facility_id: str, key: str) -> Estimate:
        den = self.profile.denominators[key]
        if den.empower_measure is not None:
            return self.empower_dme(facility_id, key)
        if den.rate is not None:
            pop = self._scoped_population(facility_id, den)
            return Estimate(
                label=f"{key} panel",
                value=pop.value * den.rate,
                formula=f"{den.scope}_in_catchment × rate[{key}] = {pop.value:.0f} × {den.rate}",
                inputs={"population": round(pop.value, 1), "scope": den.scope, "rate": den.rate},
                sources=[den.source],
                caveats=[den.basis, ESTIMATE_CAVEAT],
                components=[pop],
            )
        vets = self.veterans(facility_id)
        if den.count is not None:
            national = self.tables.national_veterans
            share = vets.value / national if national else 0.0
            return Estimate(
                label=f"{key} panel",
                value=den.count * share,
                formula=(
                    f"national_count[{key}] × veterans_in_catchment / national_veterans = "
                    f"{den.count} × {vets.value:.0f} / {national}"
                ),
                inputs={
                    "national_count": den.count,
                    "veterans_in_catchment": vets.value,
                    "national_veterans": national,
                },
                sources=[den.source, self.tables.vetpop_source],
                caveats=[
                    den.basis,
                    "National count allocated by veteran share (no regional variation).",
                    ESTIMATE_CAVEAT,
                ],
                components=[vets],
            )
        return self._places_panel(facility_id, key, den, vets)

    def _places_panel(
        self, facility_id: str, key: str, den: Denominator, vets: Estimate
    ) -> Estimate:
        station, _ = self.station_for(facility_id)
        counties = self.catchment.get(station, [])
        measure = den.places_measure or ""
        if measure not in self.tables.places_measures:
            raise ValueError(
                f"denominator '{key}': PLACES measure {measure!r} is not a column of the "
                f"reference table (have {sorted(self.tables.places_measures)})"
            )
        fallback = self.tables.national_places_rate(measure)
        total = 0.0
        missing = 0
        for c in counties:
            n = self.tables.veterans.get(c, 0)
            rate = (self.tables.places.get(c) or {}).get(measure)
            if rate is None:
                missing += 1
                rate = fallback or 0.0
            total += n * rate / 100.0
        caveats = [den.basis, PLACES_CAVEAT, ESTIMATE_CAVEAT]
        if missing:
            caveats.append(
                f"{missing} of {len(counties)} counties lack the PLACES measure; "
                "national veteran-weighted mean used."
            )
        return Estimate(
            label=f"{key} panel",
            value=total,
            formula=(
                f"Σ_county veterans(c) × PLACES {measure}(c) / 100 over {len(counties)} counties"
            ),
            inputs={
                "measure": measure,
                "counties": len(counties),
                "fallback_rate_pct": round(fallback or 0.0, 2),
            },
            sources=[den.source, self.tables.places_source],
            caveats=caveats,
            components=[vets],
        )

    # ------------------------------------------------------------------ cards

    def _share_estimate(
        self, label: str, base: Estimate, key: str, notes: list[str | None]
    ) -> Estimate:
        share = self.profile.denominators[key]
        rate = share.rate or 0.0
        return Estimate(
            label=label,
            value=base.value * rate,
            formula=f"condition_panel × share[{key}] = {base.value:.0f} × {rate}",
            inputs={"condition_panel": round(base.value, 1), "share": rate, "share_key": key},
            sources=[share.source],
            caveats=[c for c in notes if c] + [ESTIMATE_CAVEAT],
            components=[base],
        )

    def _upper_bound(
        self, label: str, base: Estimate, notes: list[str | None], *, has_class: bool = True
    ) -> Estimate:
        bound = (
            "Upper bound: whole condition panel stands in for the medication/device class."
            if has_class
            else "Condition panel (the card selects on conditions, not on a medication class)."
        )
        return Estimate(
            label=label,
            value=base.value,
            formula="condition_panel"
            + (" (no medication/device-class share in the profile)" if has_class else ""),
            inputs={"condition_panel": round(base.value, 1)},
            sources=base.sources,
            caveats=[c for c in notes if c] + [bound, ESTIMATE_CAVEAT],
            components=[base],
        )

    def card_panel(self, facility_id: str, card: Card) -> Estimate:
        """The card's affected panel: condition panel × profile class share (if any), with
        sub-panels as components."""
        sel = card.population_selector
        base = self.condition_panel(facility_id, sel.denominator_key)
        label = f"{card.title} — affected panel"
        has_class = bool(sel.all_med_classes() or sel.device_classes)
        mult = self.profile.panel_multipliers.get(card.id)
        if mult is not None:
            panel = self._share_estimate(label, base, mult.denominator_key, [mult.note])
        else:
            panel = self._upper_bound(label, base, [], has_class=has_class)
        unsized: list[str] = []
        for sp in sel.sub_panels:
            sub_label = f"{sp.label} (sub-panel)"
            if sp.denominator_key and (
                self.profile.denominators[sp.denominator_key].empower_measure is not None
            ):
                # a measured exposure layer, not a share of the condition panel
                measured = self.empower_dme(facility_id, sp.denominator_key)
                panel.components.append(
                    measured.model_copy(
                        update={
                            "label": f"{sub_label}: {measured.label}",
                            "caveats": [c for c in [sp.note] if c] + measured.caveats,
                        }
                    )
                )
            elif sp.denominator_key and self.profile.denominators[sp.denominator_key].share:
                panel.components.append(
                    self._share_estimate(sub_label, base, sp.denominator_key, [sp.note])
                )
            elif sp.denominator_key:  # a population panel of its own (rate, count or PLACES)
                own = self.condition_panel(facility_id, sp.denominator_key)
                panel.components.append(
                    own.model_copy(
                        update={
                            "label": f"{sub_label}: {own.label}",
                            "caveats": [c for c in [sp.note] if c] + own.caveats,
                        }
                    )
                )
            else:
                # No reviewed denominator for this sub-panel: say so rather than lend it the
                # whole condition panel (the OUD sub-panel of Card 3 is not a schizophrenia
                # count).
                unsized.append(sp.label)
        if unsized:
            panel.caveats.insert(
                0,
                "Not sized — no reviewed denominator in the profile for: "
                + "; ".join(unsized)
                + ".",
            )
        # A card that selects on several conditions (Card 7: CHD or HF or COPD or asthma) has
        # overlapping panels that cannot be summed; the headline is the largest single
        # condition panel and says so, instead of whichever key happens to be primary.
        standalone = (
            [c for c in panel.components[1:] if c.unit == panel.unit and "sub-panel" in c.label]
            if mult is None
            else []
        )
        largest = max(standalone, key=lambda c: c.value, default=None)
        if largest is not None and largest.value > panel.value:
            panel = panel.model_copy(
                update={
                    "value": largest.value,
                    "formula": (
                        f"max(condition_panel, sub-panels) = "
                        f"{largest.label.split(' (sub-panel)')[0]} ({largest.value:.0f}); "
                        "conditions overlap, so the union is not estimable and this is a "
                        "lower bound"
                    ),
                    "inputs": {
                        **panel.inputs,
                        "largest_panel": largest.label,
                        "largest_value": round(largest.value, 1),
                    },
                    "caveats": [
                        "Lower bound: the largest single-condition panel; the card's conditions "
                        "overlap and no union estimate exists."
                    ]
                    + [c for c in panel.caveats if not c.startswith("Condition panel")],
                }
            )
        return panel

    # ------------------------------------------------------------------ sanity

    def national_totals(self, cards: list[Card]) -> dict[str, float]:
        totals: dict[str, float] = {"veterans_total": float(self.tables.national_veterans)}
        for key in {c.population_selector.denominator_key for c in cards}:
            totals[f"panel:{key}"] = sum(self.condition_panel(f, key).value for f in self.catchment)
        return totals

    def check_national_anchors(self, cards: list[Card]) -> list[str]:
        """Return anchor violations (empty = all within tolerance)."""
        totals = self.national_totals(cards)
        observed = {
            "veterans_total": totals["veterans_total"],
            "vha_heart_failure_patients": totals.get("panel:heart_failure"),
        }
        problems = []
        for name, anchor in self.profile.national_anchors.items():
            got = observed.get(name)
            if got is None:
                continue
            dev = abs(got - anchor.value) / anchor.value
            if dev > anchor.tolerance:
                problems.append(
                    f"{name}: {got:,.0f} vs anchor {anchor.value:,.0f} "
                    f"(±{anchor.tolerance:.0%}), off by {dev:.0%}"
                )
        return problems
