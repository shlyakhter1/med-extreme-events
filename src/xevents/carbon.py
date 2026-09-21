"""Medication carbon-footprint estimates for display (``docs/carbon.yaml``).

Display-only, order-of-magnitude figures from published pharmaceutical life-cycle
assessments and analogues; ``docs/carbon-footprint.md`` holds the methods and references.
Every number carries its range, basis and confidence, and the file's own
``ui_disclaimer`` must be rendered wherever these appear — the same provenance rule the
panel estimates follow. Nothing here may influence clinical content or card triggering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
CARBON_PATH = REPO_ROOT / "docs" / "carbon.yaml"

Range = Annotated[list[float], Field(min_length=2, max_length=2)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


class CarbonError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CarbonSource(_Strict):
    ref: NonEmptyStr
    url: HttpUrl | None = None


class CarbonAssumptions(_Strict):
    manufacturing_location: NonEmptyStr
    cn_in_api_multiplier: Range
    car_kg_co2e_per_km: float = Field(gt=0)
    scope: NonEmptyStr


class CarbonEntry(_Strict):
    """One drug or therapy. Ranges are honest bounds, not precision."""

    card: int = Field(
        ge=1, description="card number in docs/card-library.md or card-library-additions.md"
    )
    key: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    drug: NonEmptyStr
    assumed_dose: NonEmptyStr
    api_g_per_patient_year: float | None = None
    basis: NonEmptyStr
    confidence: NonEmptyStr
    kg_co2e_per_patient_year: Range
    km_driven_equivalent_per_year: Range
    g_co2e_per_daily_dose: Range | None = None
    g_co2e_per_injection: Range | None = None
    kg_co2e_per_session: Range | None = None
    kg_co2e_per_session_literature_range: Range | None = None
    note: str | None = None
    sources: list[NonEmptyStr] = Field(min_length=1)

    @model_validator(mode="after")
    def ranges_ordered(self) -> Self:
        for name in (
            "kg_co2e_per_patient_year",
            "km_driven_equivalent_per_year",
            "g_co2e_per_daily_dose",
            "g_co2e_per_injection",
            "kg_co2e_per_session",
        ):
            value = getattr(self, name)
            if value is not None and value[0] > value[1]:
                raise ValueError(f"{name}: low bound {value[0]} exceeds high bound {value[1]}")
        return self

    def annual_tonnes(self, patients: float) -> tuple[float, float]:
        """Panel-scaled tonnes CO2e per year (low, high). Patients is an estimate, so the
        output inherits that uncertainty on top of the footprint range."""
        lo, hi = self.kg_co2e_per_patient_year
        return (patients * lo / 1000.0, patients * hi / 1000.0)


class CarbonTable(_Strict):
    ui_disclaimer: NonEmptyStr
    assumptions: CarbonAssumptions
    entries: list[CarbonEntry] = Field(min_length=1)
    sources: dict[str, CarbonSource] = Field(min_length=1)

    @model_validator(mode="after")
    def sources_resolve(self) -> Self:
        known = set(self.sources)
        for e in self.entries:
            unknown = [s for s in e.sources if s not in known]
            if unknown:
                raise ValueError(f"entry '{e.key}' cites unknown sources {unknown}")
        keys = [e.key for e in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate entry keys: {keys}")
        return self

    def for_card_number(self, number: int) -> list[CarbonEntry]:
        return [e for e in self.entries if e.card == number]

    def citations(self, entry: CarbonEntry) -> list[str]:
        return [self.sources[s].ref for s in entry.sources]


def load_carbon(path: Path = CARBON_PATH) -> CarbonTable:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CarbonError(f"{path}: carbon table not found") from exc
    except yaml.YAMLError as exc:
        raise CarbonError(f"{path}: YAML parse error: {exc}") from exc
    try:
        return CarbonTable.model_validate(raw)
    except ValidationError as exc:
        raise CarbonError(f"{path}: {exc}") from exc
