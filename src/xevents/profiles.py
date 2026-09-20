"""Population profile loader (``profiles/*.yaml``).

The profile owns every population-specific fact the engine needs: denominator anchors,
acuity ordering, notification channels, care-system hooks. Cards reference profile keys;
they never restate the numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from xevents.models import Card

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


class ProfileValidationError(ValueError):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Denominator(_Strict):
    """Exactly one of: a rate (share of the profile population), an absolute national
    count (allocated to facilities by veteran share), or a PLACES county measure name
    (county-specific crude prevalence among adults, general population)."""

    rate: float | None = Field(default=None, ge=0.0, le=1.0)
    count: int | None = Field(default=None, ge=0)
    places_measure: str | None = Field(default=None, pattern=r"^[a-z]+$")
    scope: Annotated[str, Field(pattern=r"^[a-z_]+$")] = Field(
        default="veterans",
        description="Population a rate applies to: 'veterans' (VetPop) or a key in "
        "profile.scopes (e.g. 'vha_users' = veterans × share_of_veterans).",
    )
    basis: Annotated[str, Field(min_length=1)]
    source: Annotated[str, Field(min_length=1)]
    note: str | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        set_ = [x is not None for x in (self.rate, self.count, self.places_measure)]
        if sum(set_) != 1:
            raise ValueError("set exactly one of rate, count or places_measure")
        return self


class PopulationScope(_Strict):
    share_of_veterans: float = Field(gt=0, le=1)
    source: Annotated[str, Field(min_length=1)]
    note: str | None = None


class Catchment(_Strict):
    anchor_classifications: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    projection_year: int = Field(ge=2023, le=2053)
    note: str | None = None


class PanelMultiplier(_Strict):
    """Medication/device-class share applied on top of a card's condition panel."""

    denominator_key: Annotated[str, Field(min_length=1)]
    note: str | None = None


class NationalAnchor(_Strict):
    value: float = Field(gt=0)
    tolerance: float = Field(default=0.20, gt=0, le=1)
    source: Annotated[str, Field(min_length=1)]


class Hook(_Strict):
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    url: HttpUrl | None = None
    phone: str | None = None


class Profile(_Strict):
    profile: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    population_label: Annotated[str, Field(min_length=1)]
    denominators: dict[str, Denominator] = Field(min_length=1)
    acuity_order: list[Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]] = Field(min_length=1)
    channels: list[Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]] = Field(min_length=1)
    hooks: dict[str, Hook] = Field(default_factory=dict)
    escalation_default: Annotated[str, Field(min_length=1)] = Field(
        description="Templated escalation used when a card's escalation.response is null."
    )
    catchment: Catchment
    min_panel_patients: float = Field(
        default=1.0,
        ge=0,
        description="A card is not issued where the estimated panel falls below this. "
        "An estimate of half a patient is not a patient.",
    )
    scopes: dict[str, PopulationScope] = Field(default_factory=dict)
    panel_multipliers: dict[str, PanelMultiplier] = Field(
        default_factory=dict, description="card id → medication-class share multiplier"
    )
    national_anchors: dict[str, NationalAnchor] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_acuity(self) -> Self:
        if len(self.acuity_order) != len(set(self.acuity_order)):
            raise ValueError(f"duplicate entries in acuity_order: {self.acuity_order}")
        return self

    @model_validator(mode="after")
    def scopes_resolve(self) -> Self:
        for key, den in self.denominators.items():
            if den.scope != "veterans" and den.scope not in self.scopes:
                raise ValueError(f"denominators[{key}].scope '{den.scope}' is not in scopes")
        return self

    def acuity_rank(self, acuity_class: str) -> int:
        """0 is highest acuity."""
        return self.acuity_order.index(acuity_class)


def load_profile(path: Path) -> Profile:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileValidationError(f"{path}: YAML parse error: {exc}") from exc
    try:
        return Profile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileValidationError(f"{path}: {exc}") from exc


def check_cards_against_profile(cards: list[Card], profile: Profile) -> list[str]:
    """Return a list of dangling references (empty means every card key resolves)."""
    problems: list[str] = []
    for card in cards:
        sel = card.population_selector
        if sel.denominator_key not in profile.denominators:
            problems.append(f"{card.id}: denominator_key '{sel.denominator_key}' not in profile")
        for sp in sel.sub_panels:
            if sp.denominator_key and sp.denominator_key not in profile.denominators:
                problems.append(
                    f"{card.id}: sub_panel '{sp.key}' denominator_key "
                    f"'{sp.denominator_key}' not in profile"
                )
        if card.acuity_class not in profile.acuity_order:
            problems.append(f"{card.id}: acuity_class '{card.acuity_class}' not in profile")
        for hook in card.care_system_hooks:
            if hook not in profile.hooks:
                problems.append(f"{card.id}: care_system_hook '{hook}' not in profile")
    for card_id, mult in profile.panel_multipliers.items():
        if card_id not in {c.id for c in cards}:
            problems.append(f"profile panel_multipliers: unknown card '{card_id}'")
        if mult.denominator_key not in profile.denominators:
            problems.append(
                f"profile panel_multipliers[{card_id}]: unknown key '{mult.denominator_key}'"
            )
    return problems
