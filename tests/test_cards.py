"""Card library: the six v1 cards load; malformed cards are rejected with useful errors."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.conftest import INVALID_CARDS
from xevents.cards import CARDS_DIR, CardValidationError, load_card, load_cards
from xevents.models import Card, EventType, EvidenceTier

EXPECTED = {
    1: ("heat-lithium", {EventType.HEAT}),
    2: ("heat-antipsychotics", {EventType.HEAT}),
    3: ("hurricane-delivery-interruption", {EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE}),
    4: ("heat-heart-failure", {EventType.HEAT}),
    5: ("outage-insulin", {EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE}),
    6: ("outage-dialysis", {EventType.HURRICANE_FLOOD, EventType.POWER_OUTAGE}),
}


def test_six_cards_load(cards: list[Card]) -> None:
    assert len(cards) == 6
    assert {c.number for c in cards} == set(EXPECTED)
    for card in cards:
        card_id, event_types = EXPECTED[card.number]
        assert card.id == card_id
        assert card.event_types == event_types


def test_card_ids_and_numbers_unique(cards: list[Card]) -> None:
    assert len({c.id for c in cards}) == 6
    assert len({c.number for c in cards}) == 6


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
    """Every patient-facing sentence must appear verbatim in the reviewed card documents
    (docs/card-library.md, or docs/card-library-additions.md for Cards 7-8 and the Card 6
    addendum)."""
    docs = CARDS_DIR.parent / "docs"
    library = (docs / "card-library.md").read_text(encoding="utf-8") + (
        docs / "card-library-additions.md"
    ).read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", library)
    for card in cards:
        for action in card.actions.patient:
            sentence = re.sub(r"\s+", " ", action.text)
            assert sentence in flat, f"{card.id}: not verbatim: {sentence!r}"


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
    assert len(load_cards(tmp_path)) == 6
    shutil.copy(INVALID_CARDS / "untiered-claim.yaml", tmp_path / "07-malformed.yaml")
    with pytest.raises(CardValidationError, match=re.escape("07-malformed.yaml")):
        load_cards(tmp_path)


def test_duplicate_card_id_is_rejected(tmp_path: Path) -> None:
    src = CARDS_DIR / "01-heat-lithium.yaml"
    shutil.copy(src, tmp_path / "a.yaml")
    shutil.copy(src, tmp_path / "b.yaml")
    with pytest.raises(CardValidationError, match="duplicate card id 'heat-lithium'"):
        load_cards(tmp_path)
