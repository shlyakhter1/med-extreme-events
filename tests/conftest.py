from __future__ import annotations

from pathlib import Path

import pytest

from xevents.cards import CARDS_DIR, load_cards
from xevents.models import Card
from xevents.profiles import PROFILES_DIR, Profile, load_profile

FIXTURES = Path(__file__).parent / "fixtures"
INVALID_CARDS = FIXTURES / "cards" / "invalid"


@pytest.fixture(scope="session")
def cards() -> list[Card]:
    return load_cards(CARDS_DIR)


@pytest.fixture(scope="session")
def va_profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")
