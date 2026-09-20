"""Domain models.

M0: the card schema (``Card`` and its parts). Event, Facility and ActionItem models
land in M1/M2/M4. Everything is Pydantic v2 with ``extra="forbid"`` so a typo in a
YAML card is a validation error, not silently ignored content.

Clinical content (patient-facing strings, escalation triggers, evidence claims) is
data in ``cards/*.yaml``; nothing here generates or rewrites it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- triggers


class EventType(StrEnum):
    HEAT = "heat"
    HURRICANE_FLOOD = "hurricane_flood"
    POWER_OUTAGE = "power_outage"
    WILDFIRE_SMOKE = "wildfire_smoke"
    AIR_POLLUTION = "air_pollution"


class HeatRiskLevel(StrEnum):
    """NWS HeatRisk categories, in increasing severity."""

    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    MAGENTA = "magenta"


class TriggerConditions(StrictModel):
    """Threshold conditions for one trigger. All set fields must hold (AND);
    a card lists several ``event_triggers`` when any one of them should fire (OR).
    """

    nws_events: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Exact NWS CAP `event` values, e.g. 'Heat Advisory'. Any listed value matches.",
    )
    heatrisk_min: HeatRiskLevel | None = Field(
        default=None, description="Fire when NWS HeatRisk is at or above this level."
    )
    aqi_min: int | None = Field(default=None, ge=0, le=500, description="AirNow AQI at or above.")
    fema_declared: bool | None = Field(
        default=None, description="Require an OpenFEMA disaster declaration for the county."
    )
    outage_forecast: bool | None = Field(
        default=None, description="Require a forecast/declared power outage for the geography."
    )

    @model_validator(mode="after")
    def at_least_one_condition(self) -> Self:
        if not any(
            [
                self.nws_events,
                self.heatrisk_min is not None,
                self.aqi_min is not None,
                self.fema_declared is not None,
                self.outage_forecast is not None,
            ]
        ):
            raise ValueError("trigger conditions must set at least one threshold")
        return self


class EventTrigger(StrictModel):
    type: EventType
    conditions: TriggerConditions


# --------------------------------------------------------------------------- population


class CodeSystem(StrEnum):
    ICD10CM = "icd10cm"
    SNOMED = "snomed"
    ATC = "atc"
    RXNORM = "rxnorm"
    VA_DRUG_CLASS = "va_drug_class"
    EMPOWER = "empower"
    LOCAL = "local"


class Coding(StrictModel):
    system: CodeSystem
    code: NonEmptyStr
    display: NonEmptyStr
    qualifier: str | None = Field(
        default=None,
        description="Free-text narrowing, e.g. 'long-acting injectable formulation'.",
    )


class SubPanel(StrictModel):
    """A named sub-population within a card (e.g. Card 3's clozapine / LAI / methadone)."""

    key: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    label: NonEmptyStr
    condition_codes: list[Coding] = Field(default_factory=list)
    med_classes: list[Coding] = Field(default_factory=list)
    device_classes: list[Coding] = Field(default_factory=list)
    flags: list[NonEmptyStr] = Field(default_factory=list)
    denominator_key: str | None = Field(
        default=None, description="Key into the profile's denominator table for this sub-panel."
    )
    note: str | None = None


class PopulationSelector(StrictModel):
    condition_codes: list[Coding] = Field(min_length=1)
    med_classes: list[Coding] = Field(default_factory=list)
    device_classes: list[Coding] = Field(default_factory=list)
    flags: list[NonEmptyStr] = Field(
        default_factory=list, description="Risk-amplifier flags, e.g. 'homeless', 'prior_aki'."
    )
    denominator_key: NonEmptyStr = Field(
        description="Key into the profile's denominator table (profiles/*.yaml)."
    )
    denominator_note: str | None = Field(
        default=None, description="Verbatim anchor text from the card library, for provenance."
    )
    sub_panels: list[SubPanel] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_sub_panel_keys(self) -> Self:
        keys = [s.key for s in self.sub_panels]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate sub_panel keys: {keys}")
        return self

    def all_med_classes(self) -> list[Coding]:
        return [*self.med_classes, *(m for s in self.sub_panels for m in s.med_classes)]


# --------------------------------------------------------------------------- actions


class Phase(StrEnum):
    PRE_EVENT = "pre_event"
    DURING_EVENT = "during_event"
    ANY = "any"


class Action(StrictModel):
    text: NonEmptyStr
    phase: Phase = Phase.ANY


class Actions(StrictModel):
    care_team: list[Action] = Field(min_length=1)
    patient: list[Action] = Field(
        min_length=1, description="Verbatim patient-facing sentences from the reviewed card."
    )
    caregiver: list[Action] = Field(
        default_factory=list,
        description="Caregiver-addressed items. Empty until reviewed content exists.",
    )


class Escalation(StrictModel):
    signs: NonEmptyStr
    response: str | None = Field(
        default=None,
        description="Verbatim response from the card; None means the profile's templated "
        "'contact your care team' escalation applies.",
    )
    emergency: bool = Field(default=False, description="True when the card says 911/ED.")


# --------------------------------------------------------------------------- evidence


class EvidenceTier(StrEnum):
    """Requirements §8 tiers. 'weak' is deliberately absent: weak/folklore claims are
    not representable and therefore cannot be published."""

    STRONG = "strong"
    INFERENTIAL = "inferential"
    EXPERT_GUIDANCE = "expert_guidance"


class Source(StrictModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    citation: NonEmptyStr
    url: HttpUrl | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    note: str | None = None


class Claim(StrictModel):
    text: NonEmptyStr
    tier: EvidenceTier
    source_ids: list[NonEmptyStr] = Field(min_length=1)


class Evidence(StrictModel):
    mechanism: NonEmptyStr
    claims: list[Claim] = Field(min_length=1)
    caveats: list[NonEmptyStr] = Field(default_factory=list)


# --------------------------------------------------------------------------- card


class WindowDays(StrictModel):
    """Actionability window: how many days before event onset the card fires."""

    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.min > self.max:
            raise ValueError("window_days.min must be <= window_days.max")
        return self


class Safety(StrictModel):
    do_not_stop_medication: bool = Field(
        description="Required True for any card with medication classes: the templated "
        "'don't stop your medication — contact your care team' message is attached."
    )
    notes: list[NonEmptyStr] = Field(default_factory=list)


class Card(StrictModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    number: int = Field(ge=1, description="Card number in docs/card-library.md.")
    title: NonEmptyStr
    summary: NonEmptyStr
    event_triggers: list[EventTrigger] = Field(min_length=1)
    population_selector: PopulationSelector
    actions: Actions
    escalation: list[Escalation] = Field(min_length=1)
    evidence_tier: EvidenceTier
    evidence: Evidence
    sources: list[Source] = Field(min_length=1)
    window_days: WindowDays
    safety: Safety
    acuity_class: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")] = Field(
        description="Key into the profile's acuity ordering."
    )
    care_system_hooks: list[NonEmptyStr] = Field(
        default_factory=list, description="Keys into the profile's care-system hooks."
    )

    @model_validator(mode="after")
    def check_sources_and_claims(self) -> Self:
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate source ids: {ids}")
        known = set(ids)
        for i, claim in enumerate(self.evidence.claims):
            unknown = [s for s in claim.source_ids if s not in known]
            if unknown:
                raise ValueError(
                    f"evidence.claims[{i}] cites unknown source ids {unknown}; "
                    f"known: {sorted(known)}"
                )
        tiers = {c.tier for c in self.evidence.claims}
        if self.evidence_tier not in tiers:
            raise ValueError(
                f"evidence_tier '{self.evidence_tier}' is not the tier of any claim "
                f"(claim tiers: {sorted(t.value for t in tiers)})"
            )
        return self

    @model_validator(mode="after")
    def check_medication_safety(self) -> Self:
        if self.population_selector.all_med_classes() and not self.safety.do_not_stop_medication:
            raise ValueError(
                "cards that select on medication classes must set "
                "safety.do_not_stop_medication: true"
            )
        return self

    @property
    def event_types(self) -> set[EventType]:
        return {t.type for t in self.event_triggers}


# --------------------------------------------------------------------------- facilities


class OperatingStatusCode(StrEnum):
    """VA Facilities API v1 ``operatingStatus.code`` values."""

    NORMAL = "NORMAL"
    NOTICE = "NOTICE"
    LIMITED = "LIMITED"
    CLOSED = "CLOSED"
    TEMPORARY_CLOSURE = "TEMPORARY_CLOSURE"
    TEMPORARY_LOCATION = "TEMPORARY_LOCATION"
    VIRTUAL_CARE = "VIRTUAL_CARE"
    COMING_SOON = "COMING_SOON"


class Facility(StrictModel):
    """A VA health facility (location tier L3) with its county/VISN attribution.

    ``visn`` comes from the Facilities API itself; ``county_fips`` is attributed from the
    physical ZIP via the ZIP↔county crosswalk and ``county_source`` records how.
    """

    id: Annotated[str, Field(pattern=r"^vha_[A-Za-z0-9]+$")]
    name: NonEmptyStr
    facility_type: NonEmptyStr
    classification: str | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    zip5: Annotated[str, Field(pattern=r"^\d{5}$")] | None = None
    city: str | None = None
    state: str | None = None
    visn: Annotated[str, Field(pattern=r"^\d{1,2}$")] | None = None
    health_care_system: str | None = None
    operating_status: OperatingStatusCode
    operating_status_info: str | None = None
    county_fips: Annotated[str, Field(pattern=r"^\d{5}$")] | None = None
    county_source: str | None = None
    market: str | None = Field(
        default=None, description="VHA market; unavailable until a county→market source exists."
    )

    @property
    def resolved(self) -> bool:
        return self.county_fips is not None and self.visn is not None
