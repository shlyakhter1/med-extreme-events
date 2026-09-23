"""Cross-card consistency rules (docs/medical-references.md §3).

One veteran can hold several cards at once (bipolar + heart failure, diabetes + ESRD), so the
cards must never contradict each other. The shared sentences are read from §3 itself, not
restated here, and each guard is mutation-checked: perturbing a card must make it fire.
"""

from __future__ import annotations

import re

import pytest

from tests.card_library import REFERENCES_PATH, flat
from xevents.engine import safety_message
from xevents.models import Action, Card
from xevents.profiles import PROFILES_DIR, load_profile


def _rule_sentence(rule: int) -> str:
    """The italic quoted sentence of §3 rule ``rule``."""
    text = REFERENCES_PATH.read_text(encoding="utf-8")
    section = text.split("## 3.", 1)[1].split("## 4.", 1)[0]
    body = re.split(r"\n(?=\d+\. )", section)[rule]
    m = re.search(r'\*"(.+?)"\*', flat(body))
    assert m, f"§3 rule {rule} has no quoted sentence"
    return m.group(1)


FLUID_LIMIT = _rule_sentence(1)
CARBON_MONOXIDE = _rule_sentence(2)
ESCAPE_HATCH = _rule_sentence(3)
INSULIN_FREEZE = (
    "If you use insulin, don't let it freeze — an unheated home or car can freeze it, and "
    "frozen insulin must be thrown away."
)
SHARED = {FLUID_LIMIT: {1, 4, 6}, CARBON_MONOXIDE: {5, 6, 7, 8}, ESCAPE_HATCH: {8}}

# A liters-per-day target in any unit: "2.5–3 L", "2,500 mL/day", "3 liters".
LITERS = re.compile(r"\d[\d.,–-]*\s*(?:L|mL|ml|liters?|litres?)\b|L/day")
# An instruction to stop, hold, skip or change a medication ("stop your lithium"); negated
# forms ("Don't stop or change your lithium", "Never skip your …") are removed first.
_VERB = r"(?:stop|hold|skip|pause|change)"
NEGATED = re.compile(rf"\b(?:don't|do not|never)\s+{_VERB}(?:\s+or\s+{_VERB})?", re.IGNORECASE)
STOP_MED = re.compile(rf"\b{_VERB}\b(?:\s+(?:taking|using))?\s+your\b", re.IGNORECASE)


def patient_text(card: Card) -> str:
    return flat(" ".join(a.text for a in card.actions.patient))


def violations(cards: list[Card]) -> list[str]:
    """Every §3 breach across ``cards``; empty means consistent."""
    by_number = {c.number: c for c in cards}
    found: list[str] = []
    for sentence, numbers in SHARED.items():
        for n in sorted(numbers):
            if sentence not in patient_text(by_number[n]):
                found.append(f"card {n} lacks shared sentence {sentence[:40]!r}")
    if INSULIN_FREEZE not in patient_text(by_number[7]):
        found.append("card 7 lacks the insulin-freeze line")
    if LITERS.search(patient_text(by_number[1])):
        found.append("card 1 patient text quotes a liters-per-day figure")
    profile = load_profile(PROFILES_DIR / "va.yaml")
    for card in cards:
        strings = [a.text for a in card.actions.patient] + [a.text for a in card.actions.caregiver]
        strings += [m for m in [safety_message(card, profile)] if m]
        for s in strings:
            if STOP_MED.search(NEGATED.sub("", s)):
                found.append(f"card {card.number} tells the patient to stop/change: {s!r}")
    return found


def _with_patient_text(card: Card, old: str, new: str) -> Card:
    actions = [Action(text=a.text.replace(old, new), phase=a.phase) for a in card.actions.patient]
    return card.model_copy(update={"actions": card.actions.model_copy(update={"patient": actions})})


def test_cards_satisfy_every_cross_card_rule(cards: list[Card]) -> None:
    assert violations(cards) == []


@pytest.mark.parametrize(
    ("number", "old", "new", "expected"),
    [
        # one character off in a shared sentence, on each card that carries one
        (1, "fluid limit", "fluid-limit", "card 1 lacks shared sentence"),
        (4, "keep to that limit", "keep to your limit", "card 4 lacks shared sentence"),
        (6, "heat plan", "plan", "card 6 lacks shared sentence"),
        (5, "camp stove", "camp-stove", "card 5 lacks shared sentence"),
        (6, "CO alarm", "carbon monoxide alarm", "card 6 lacks shared sentence"),
        (7, "even with the door open", "even with a door open", "card 7 lacks shared sentence"),
        (8, "in a garage", "in the garage", "card 8 lacks shared sentence"),
        (8, "cleaner-air or cooling center", "cooling center", "card 8 lacks shared sentence"),
        (7, "frozen insulin must be thrown away", "frozen insulin is risky", "insulin-freeze"),
        (1, "Drink regularly", "Drink 2.5–3 L a day", "liters-per-day"),
        (1, "Don't stop or change your lithium", "Stop your lithium", "stop/change"),
        (5, "Don't skip your insulin", "Skip your insulin", "stop/change"),
    ],
)
def test_guard_fires_when_a_card_is_perturbed(
    cards: list[Card], number: int, old: str, new: str, expected: str
) -> None:
    """Mutation check: each rule is live, not vacuously green."""
    target = next(c for c in cards if c.number == number)
    assert old in patient_text(target), f"mutation anchor {old!r} missing from card {number}"
    mutated = [_with_patient_text(c, old, new) if c.number == number else c for c in cards]
    found = violations(mutated)
    assert any(expected in v for v in found), found


def test_shared_sentences_are_read_from_the_reference_index() -> None:
    assert FLUID_LIMIT.startswith("If a doctor has given you a fluid limit")
    assert CARBON_MONOXIDE.endswith("Use a battery-powered CO alarm.")
    assert ESCAPE_HATCH == "If it gets too hot inside, go to a cleaner-air or cooling center."
