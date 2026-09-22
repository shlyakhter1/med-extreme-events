from __future__ import annotations

import os
from pathlib import Path

import pytest

from xevents.cards import CARDS_DIR, load_cards
from xevents.models import Card
from xevents.profiles import PROFILES_DIR, Profile, load_profile

FIXTURES = Path(__file__).parent / "fixtures"
INVALID_CARDS = FIXTURES / "cards" / "invalid"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """``network``-marked tests hit live services; they run only with RUN_NETWORK_TESTS=1,
    whatever keys happen to be in .env."""
    if os.environ.get("RUN_NETWORK_TESTS"):
        return
    skip = pytest.mark.skip(reason="network test: set RUN_NETWORK_TESTS=1")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def cards() -> list[Card]:
    return load_cards(CARDS_DIR)


@pytest.fixture(scope="session")
def va_profile() -> Profile:
    return load_profile(PROFILES_DIR / "va.yaml")
