"""Card library: the eight cards load; malformed cards are rejected with useful errors."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.card_library import (
    SHARED_MARKER,
    flat,
    library_text,
    reference_index,
    sources_by_card,
)
from tests.conftest import INVALID_CARDS
from xevents.cards import CARDS_DIR, CardValidationError, load_card, load_cards
from xevents.models import Card, EventType, EvidenceTier

EXPECTED = {
    1: ("heat-lithium", {EventType.HEAT}),
    2: ("heat-antipsychotics", {EventType.HEAT}),
    3: ("hurricane-delivery-interruption", {EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE}),
    4: ("heat-heart-failure", {EventType.HEAT}),
    5: (
        "outage-insulin",
        {EventType.HURRICANE_FLOOD, EventType.HIGH_WIND, EventType.POWER_OUTAGE},
    ),
    6: (
        "outage-dialysis",
        {EventType.HURRICANE_FLOOD, EventType.HIGH_WIND, EventType.POWER_OUTAGE},
    ),
    7: ("cold-cardio-respiratory", {EventType.EXTREME_COLD}),
    8: ("smoke-copd-asthma", {EventType.AIR_POLLUTION, EventType.WILDFIRE_SMOKE}),
}


def test_eight_cards_load(cards: list[Card]) -> None:
    assert len(cards) == 8
    assert {c.number for c in cards} == set(EXPECTED)
    for card in cards:
        card_id, event_types = EXPECTED[card.number]
        assert card.id == card_id
        assert card.event_types == event_types


def test_card_ids_and_numbers_unique(cards: list[Card]) -> None:
    assert len({c.id for c in cards}) == 8
    assert len({c.number for c in cards}) == 8


def test_every_claim_is_tiered_and_sourced(cards: list[Card]) -> None:
    for card in cards:
        source_ids = {s.id for s in card.sources}
        for claim in card.evidence.claims:
            assert claim.tier in EvidenceTier
            assert claim.source_ids
            assert set(claim.source_ids) <= source_ids


def test_medication_cards_carry_do_not_stop_flag(cards: list[Card]) -> None:
    for card in cards:
        if card.population_selector.all_med_classes():
            assert card.safety.do_not_stop_medication, card.id


def test_every_card_has_all_three_action_lists(cards: list[Card]) -> None:
    for card in cards:
        assert card.actions.care_team
        assert card.actions.patient
        assert isinstance(card.actions.caregiver, list)
        assert card.escalation


def test_heat_cards_share_trigger_vocabulary(cards: list[Card]) -> None:
    """Cards 1, 2 and 4 fire on the same NWS heat products (card library: 'Same as card 1')."""
    heat = {c.number: c for c in cards if c.number in (1, 2, 4)}
    nws = {n: sorted(t.conditions.nws_events for t in c.event_triggers) for n, c in heat.items()}
    assert nws[1] == nws[2] == nws[4]
    assert any("Heat Advisory" in events for events in nws[1])


def test_patient_strings_are_verbatim_from_card_library(cards: list[Card]) -> None:
    """Every patient-facing sentence must appear verbatim in the card library
    (docs/card-library.md), with library markup ([SHARED], claim markers) stripped."""
    library = library_text()
    for card in cards:
        for action in card.actions.patient:
            sentence = flat(action.text)
            assert sentence in library, f"{card.id}: not verbatim: {sentence!r}"


def test_care_team_and_escalation_strings_are_verbatim(cards: list[Card]) -> None:
    """Care-team actions, escalation signs/responses, claims and caveats are reviewed text
    too; they must come from the library, not be rewritten at transcription."""
    library = library_text()
    for card in cards:
        strings = [a.text for a in card.actions.care_team]
        strings += [e.signs for e in card.escalation]
        strings += [e.response for e in card.escalation if e.response]
        strings += [c.text for c in card.evidence.claims]
        strings += card.evidence.caveats
        for s in strings:
            assert flat(s) in library, f"{card.id}: not in the library: {s!r}"


def test_no_rendered_string_carries_library_markup(cards: list[Card]) -> None:
    """[SHARED] is library markup; it must never reach YAML strings (and so the UI)."""
    for card in cards:
        dumped = card.model_dump_json()
        assert SHARED_MARKER not in dumped, card.id
        assert "[strong |" not in dumped and "[inferential |" not in dumped, card.id


# --------------------------------------------------------------------------- rejection


@pytest.mark.parametrize(
    ("filename", "expected_fragment"),
    [
        ("untiered-claim.yaml", "evidence.claims.1.tier: Field required"),
        ("weak-tier.yaml", "evidence_tier"),
        ("unknown-source.yaml", "unknown source ids ['does-not-exist']"),
        ("med-card-without-safety.yaml", "safety.do_not_stop_medication: true"),
        ("unknown-field.yaml", "escalations: Extra inputs are not permitted"),
        ("not-yaml.yaml", "YAML parse error"),
    ],
)
def test_malformed_card_is_rejected_with_useful_error(
    filename: str, expected_fragment: str
) -> None:
    path = INVALID_CARDS / filename
    with pytest.raises(CardValidationError) as excinfo:
        load_card(path)
    message = str(excinfo.value)
    assert str(path) in message, "error must name the offending file"
    assert expected_fragment in message, message


def test_unknown_field_error_also_reports_empty_trigger() -> None:
    with pytest.raises(CardValidationError) as excinfo:
        load_card(INVALID_CARDS / "unknown-field.yaml")
    assert "at least one threshold" in str(excinfo.value)


def test_seventh_malformed_card_poisons_directory_load(tmp_path: Path) -> None:
    """A directory with the six good cards plus one malformed card must fail to load."""
    for src in CARDS_DIR.glob("*.yaml"):
        shutil.copy(src, tmp_path / src.name)
    assert len(load_cards(tmp_path)) == 8
    shutil.copy(INVALID_CARDS / "untiered-claim.yaml", tmp_path / "07-malformed.yaml")
    with pytest.raises(CardValidationError, match=re.escape("07-malformed.yaml")):
        load_cards(tmp_path)


def test_duplicate_card_id_is_rejected(tmp_path: Path) -> None:
    src = CARDS_DIR / "01-heat-lithium.yaml"
    shutil.copy(src, tmp_path / "a.yaml")
    shutil.copy(src, tmp_path / "b.yaml")
    with pytest.raises(CardValidationError, match="duplicate card id 'heat-lithium'"):
        load_cards(tmp_path)


def test_medical_references_index_every_card_source(cards: list[Card]) -> None:
    """Every id a card cites is in the medical-references §1 index (the loader's id set)."""
    index = reference_index()
    missing = sorted({s.id for c in cards for s in c.sources if s.id not in index})
    assert not missing, f"add to docs/medical-references.md §1: {missing}"


def test_card_sources_match_references_by_card_table(cards: list[Card]) -> None:
    """medical-references §2 is the card-by-card view of the YAML; they must agree exactly."""
    table = sources_by_card()
    for card in cards:
        assert {s.id for s in card.sources} == table[card.number], card.id


def test_no_quantitative_claim_rests_on_pending_sources(cards: list[Card]) -> None:
    """medical-references §5: pending sources support no quantitative claim until confirmed.
    A claim with a figure in it must cite at least one verified source (Card 1's NSAID
    figures cite finley-1995, verified, beside the pending class labeling)."""
    index = reference_index()
    for card in cards:
        for claim in card.evidence.claims:
            if not re.search(r"(?<![A-Za-z0-9.])\d", claim.text):  # a figure, not "PM2.5"
                continue
            verified = [s for s in claim.source_ids if index.get(s) == "verified"]
            assert verified, f"{card.id}: figures rest on pending sources: {claim.text!r}"


# TODO(after one green release): delete this assertion (implementation-plan-clinical M11 §1).
REMOVED_SOURCE_IDS = {
    "kelman-lurie-2015",
    "va-sandy-dialysis-study",
    "martin-latry",
    "katrina-sandy-otp-studies",
    "samhsa-otp-disaster-guidance",
    "cms-kcer-emergency-diet",
    "lithium-interaction-pharmacology",
    "fda-clozapine-rems-elimination",
    "clozapine-withdrawal-literature",
    "morris-paliperidone",
    "cdc-mmwr-72-34-2023",
    "cdc-smoke-day-asthma-2023",
    "cdc-co-texas-2021",
    "ali-dogar-2025",
    "cdc-mmwr-puerto-rico",
}


def test_no_card_cites_a_removed_source_id(cards: list[Card]) -> None:
    for card in cards:
        cited = {s.id for s in card.sources}
        cited |= {i for c in card.evidence.claims for i in c.source_ids}
        assert not cited & REMOVED_SOURCE_IDS, (card.id, sorted(cited & REMOVED_SOURCE_IDS))
    assert not REMOVED_SOURCE_IDS & set(reference_index())


def test_setoguchi_hennessy_only_on_card_5(cards: list[Card]) -> None:
    citing = {c.number for c in cards if any(s.id == "setoguchi-hennessy-2026" for s in c.sources)}
    assert citing == {5}
