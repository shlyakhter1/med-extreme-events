"""profiles/va.yaml loads and every card reference into it resolves."""

from __future__ import annotations

from xevents.models import Card
from xevents.profiles import Profile, check_cards_against_profile


def test_va_profile_loads(va_profile: Profile) -> None:
    assert va_profile.profile == "va"
    assert va_profile.acuity_order[0] == "dialysis"
    assert va_profile.denominators["diabetes"].rate == 0.25
    assert va_profile.denominators["dialysis"].count == 52000


def test_cards_resolve_against_profile(cards: list[Card], va_profile: Profile) -> None:
    assert check_cards_against_profile(cards, va_profile) == []


def test_acuity_ranking_puts_dialysis_first(cards: list[Card], va_profile: Profile) -> None:
    ranked = sorted(cards, key=lambda c: va_profile.acuity_rank(c.acuity_class))
    assert [c.id for c in ranked[:3]] == [
        "outage-dialysis",
        "hurricane-delivery-interruption",
        "outage-insulin",
    ]
