"""Domain models.

M0: the card schema (``Card`` and its parts). Event, Facility and ActionItem models
land in M1/M2/M4. Everything is Pydantic v2 with ``extra="forbid"`` so a typo in a
YAML card is a validation error, not silently ignored content.

Clinical content (patient-facing strings, escalation triggers, evidence claims) is
data in ``cards/*.yaml``; nothing here generates or rewrites it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- triggers


class EventType(StrEnum):
    HEAT = "heat"
    EXTREME_COLD = "extreme_cold"  # cold and winter-storm products (post-2024 NWS taxonomy)
    HURRICANE_FLOOD = "hurricane_flood"
    HIGH_WIND = "high_wind"  # forecast outage risk (Cards 5/6); observed loss is POWER_OUTAGE
    POWER_OUTAGE = "power_outage"
    WILDFIRE_SMOKE = "wildfire_smoke"
    AIR_POLLUTION = "air_pollution"


class SmokeDensity(StrEnum):
    """NOAA HMS smoke-analysis density classes, in increasing order."""

    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"


class HeatRiskLevel(StrEnum):
    """NWS HeatRisk categories, in increasing severity."""

    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    MAGENTA = "magenta"


class Temporality(StrEnum):
    """Forecast-vs-observed axis of an event (requirements v2 §1). Every provider maps its
    own vocabulary onto these three values; the raw basis is kept in ``Event.metrics``."""

    FORECAST = "forecast"  # event may occur; days of lead time
    IMMINENT = "imminent"  # event expected/beginning; hours of lead time
    OBSERVED = "observed"  # event measured as occurring now


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
    smoke_density_min: SmokeDensity | None = Field(
        default=None, description="Fire when NOAA HMS smoke density over the county is at or above."
    )
    fema_declared: bool | None = Field(
        default=None, description="Require an OpenFEMA disaster declaration for the county."
    )
    temporality: Temporality | None = Field(
        default=None,
        description="When set, the event's temporality (forecast/imminent/observed) must match.",
    )
    outage_pct_min: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Percent of county electric customers out (EAGLE-I) at or above.",
    )
    sustained_polls_min: int | None = Field(
        default=None,
        ge=1,
        description="The metric thresholds must hold for this many consecutive provider polls "
        "(contiguous events for the same source/type/geography) before the trigger fires.",
    )

    @property
    def has_metric_threshold(self) -> bool:
        return any(
            v is not None
            for v in (self.heatrisk_min, self.aqi_min, self.smoke_density_min, self.outage_pct_min)
        )

    @model_validator(mode="after")
    def at_least_one_condition(self) -> Self:
        if not any(
            [
                self.nws_events,
                self.has_metric_threshold,
                self.fema_declared is not None,
                self.temporality is not None,
            ]
        ):
            raise ValueError("trigger conditions must set at least one threshold")
        if self.sustained_polls_min is not None and not self.has_metric_threshold:
            raise ValueError(
                "sustained_polls_min needs a metric threshold to sustain "
                "(heatrisk_min, aqi_min, smoke_density_min or outage_pct_min)"
            )
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


# --------------------------------------------------------------------------- events


class EventSource(StrEnum):
    NWS = "nws"
    AIRNOW = "airnow"
    HMS = "hms"
    OPENFEMA = "openfema"
    EAGLE_I = "eagle_i"
    REPLAY = "replay"


class CapSeverity(StrEnum):
    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class CapUrgency(StrEnum):
    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"


class CapCertainty(StrEnum):
    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


class EventGeography(StrictModel):
    """Geography keys per requirements §5: county FIPS (L1) is the join key for matching;
    zones/ZIPs/polygons are kept for provenance and finer joins."""

    county_fips: list[Annotated[str, Field(pattern=r"^\d{5}$")]] = Field(default_factory=list)
    ugc: list[Annotated[str, Field(pattern=r"^[A-Z]{2}[CZ]\d{3}$")]] = Field(default_factory=list)
    zips: list[Annotated[str, Field(pattern=r"^\d{5}$")]] = Field(default_factory=list)
    states: list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] = Field(default_factory=list)
    polygon: dict[str, Any] | None = Field(default=None, description="GeoJSON geometry, if any")
    area_desc: str | None = None
    note: str | None = Field(default=None, description="How counties were derived, if indirect")


class Event(StrictModel):
    """CAP-derived normalized event. ``event_key`` (source + source_id) is the natural key
    for upserts; a strengthened alert replaces its predecessor rather than duplicating it."""

    source: EventSource
    source_id: NonEmptyStr
    event_type: EventType
    event_name: NonEmptyStr = Field(description="Source vocabulary, e.g. NWS 'Heat Advisory'")
    headline: str | None = None
    severity: CapSeverity = CapSeverity.UNKNOWN
    urgency: CapUrgency = CapUrgency.UNKNOWN
    certainty: CapCertainty = CapCertainty.UNKNOWN
    temporality: Temporality = Field(
        description="Required, no default: a provider that fails to map it fails validation."
    )
    onset: datetime
    expires: datetime
    sent: datetime | None = None
    geography: EventGeography
    metrics: dict[str, float | int | str] = Field(
        default_factory=dict, description="e.g. aqi, heatrisk, smoke_density, fema_disaster_number"
    )
    scenario: str | None = Field(default=None, description="Replay scenario id, else None")
    raw_ref: str | None = Field(default=None, description="Path or URL of the raw payload")

    @property
    def event_key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @model_validator(mode="after")
    def window_ordered(self) -> Self:
        if self.expires < self.onset:
            raise ValueError("expires must be >= onset")
        return self


class TimeWindow(StrictModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


# --------------------------------------------------------------------------- estimates


class EstimateKind(StrEnum):
    """Where a panel number comes from, shown in the provenance popover so the three are never
    confused (implementation-plan-clinical M12 §3)."""

    PLANNING_ESTIMATE = "planning_estimate"  # VA planning anchor (va-*-prevalence) × catchment
    MODELED_ESTIMATE = "modeled_estimate"  # CDC PLACES county prevalence × VetPop
    MEASURED = "measured"  # emPOWER measured Medicare counts


class Estimate(StrictModel):
    """A sized aggregate with its provenance: every number the UI shows carries the
    formula and inputs that produced it (requirements G2/G9; CLAUDE.md constraint 1)."""

    label: NonEmptyStr
    value: float = Field(ge=0)
    unit: NonEmptyStr = "veterans"
    kind: EstimateKind | None = Field(
        default=None,
        description="Provenance class of the number; None for building blocks (veteran counts).",
    )
    formula: NonEmptyStr
    inputs: dict[str, float | int | str] = Field(default_factory=dict)
    sources: list[NonEmptyStr] = Field(default_factory=list)
    caveats: list[NonEmptyStr] = Field(default_factory=list)
    components: list[Estimate] = Field(default_factory=list)


# --------------------------------------------------------------------------- action items


class Role(StrEnum):
    CARE_TEAM = "care_team"
    PATIENT = "patient"
    CAREGIVER = "caregiver"


class ActionItemStatus(StrEnum):
    ISSUED = "issued"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


ALLOWED_TRANSITIONS: dict[ActionItemStatus, set[ActionItemStatus]] = {
    ActionItemStatus.ISSUED: {
        ActionItemStatus.DELIVERED,
        ActionItemStatus.ACKNOWLEDGED,
        ActionItemStatus.EXPIRED,
        ActionItemStatus.SUPERSEDED,
    },
    ActionItemStatus.DELIVERED: {
        ActionItemStatus.ACKNOWLEDGED,
        ActionItemStatus.EXPIRED,
        ActionItemStatus.SUPERSEDED,
    },
    ActionItemStatus.ACKNOWLEDGED: {
        ActionItemStatus.COMPLETED,
        ActionItemStatus.EXPIRED,
        ActionItemStatus.SUPERSEDED,
    },
    ActionItemStatus.COMPLETED: set(),
    ActionItemStatus.EXPIRED: set(),
    ActionItemStatus.SUPERSEDED: set(),
}


class ActionItem(StrictModel):
    """One row per (event, card, facility, role) — requirements §7. Content is copied
    verbatim from the card so an item is self-contained for delivery and audit."""

    id: NonEmptyStr = Field(description="Natural key: event_key|card_id|facility_id|role")
    event_key: NonEmptyStr
    event_type: EventType
    event_name: NonEmptyStr
    event_severity: CapSeverity
    event_temporality: Temporality
    phase: Phase = Field(
        description="Derived from the event: forecast/imminent → pre_event, observed → "
        "during_event. ``actions`` holds that phase's actions plus the phase-agnostic ones."
    )
    card_id: NonEmptyStr
    card_version: NonEmptyStr
    card_title: NonEmptyStr
    scope_type: Literal["facility"] = "facility"
    scope_id: NonEmptyStr
    role: Role
    actions: list[Action]
    message: str | None = Field(
        default=None, description="Patient/caregiver: the verbatim card sentences joined."
    )
    escalation: list[Escalation]
    safety_message: str | None = Field(
        default=None, description="Profile-templated do-not-stop / escalation line."
    )
    evidence_tier: EvidenceTier
    sources: list[NonEmptyStr]
    panel: Estimate | None = None
    exposure: Estimate | None = Field(
        default=None,
        description="Measured exposure layer shown beside the panel (emPOWER electricity-"
        "dependent Medicare beneficiaries) on outage-triggered items; never replaces panel.",
    )
    rank_score: float = Field(
        default=0.0,
        ge=0,
        description="Within an acuity class, larger ranks first. Panel size by default; for "
        "outage events outage_pct × emPOWER count (measured × measured).",
    )
    rank_formula: str = Field(default="panel", description="How rank_score was computed.")
    acuity_class: NonEmptyStr
    acuity_rank: int = Field(ge=0)
    compounding_events: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Event keys of co-occurring events in the same county (requirements v2 "
        "§4): on heat/cold items the observed outage that raised their acuity by the "
        "profile's boost step; on outage items the concurrent heat/cold event (annotation only).",
    )
    window_start: datetime
    window_end: datetime
    status: ActionItemStatus = ActionItemStatus.ISSUED
    superseded_by: str | None = None
    scenario: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None

    @property
    def natural_key(self) -> tuple[str, str, str, str]:
        return (self.event_key, self.card_id, self.scope_id, self.role.value)
