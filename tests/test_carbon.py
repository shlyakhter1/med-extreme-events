"""Medication carbon-footprint display data: schema, provenance, and panel scaling."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from xevents.carbon import CARBON_PATH, CarbonError, CarbonTable, load_carbon
from xevents.cards import load_cards


@pytest.fixture(scope="module")
def table() -> CarbonTable:
    return load_carbon()


def test_loads_and_every_entry_is_sourced(table: CarbonTable) -> None:
    assert len(table.entries) >= 12
    known = set(table.sources)
    for e in table.entries:
        assert e.sources and set(e.sources) <= known, e.key
        assert table.citations(e), e.key
        assert e.confidence, e.key
        assert e.assumed_dose, "a dose assumption is a parameter to show, not to hide"


def test_ranges_are_ordered_and_disclaimer_present(table: CarbonTable) -> None:
    for e in table.entries:
        lo, hi = e.kg_co2e_per_patient_year
        assert 0 < lo <= hi
        klo, khi = e.km_driven_equivalent_per_year
        assert 0 < klo <= khi
    assert "never for clinical decisions" in table.ui_disclaimer


def test_every_card_number_has_carbon_rows(table: CarbonTable) -> None:
    """Each of the six cards must have at least one therapy costed, or the panel is empty."""
    for card in load_cards():
        assert table.for_card_number(card.number), f"card {card.number} ({card.id}) has no rows"


def test_dialysis_dominates_as_the_methods_doc_says(table: CarbonTable) -> None:
    dialysis = table.for_card_number(6)[0]
    orals = [e for e in table.for_card_number(4)]
    assert dialysis.kg_co2e_per_patient_year[0] >= 100 * max(
        o.kg_co2e_per_patient_year[1] for o in orals
    ), "the carbon story of this card set is dialysis ≈ 300–500× a generic pill"
    assert dialysis.confidence == "high"
    assert dialysis.kg_co2e_per_session is not None


def test_panel_scaling(table: CarbonTable) -> None:
    dialysis = table.for_card_number(6)[0]
    lo, hi = dialysis.annual_tonnes(253)
    assert round(lo) == 961 and round(hi) == 1214
    assert dialysis.annual_tonnes(0) == (0.0, 0.0)


def test_rejects_a_malformed_table(tmp_path: Path) -> None:
    raw = yaml.safe_load(CARBON_PATH.read_text(encoding="utf-8"))
    raw["entries"][0]["sources"] = ["not-a-real-source"]
    bad = tmp_path / "carbon.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(CarbonError, match="unknown sources"):
        load_carbon(bad)

    raw2 = yaml.safe_load(CARBON_PATH.read_text(encoding="utf-8"))
    raw2["entries"][0]["kg_co2e_per_patient_year"] = [50, 5]
    bad2 = tmp_path / "carbon2.yaml"
    bad2.write_text(yaml.safe_dump(raw2), encoding="utf-8")
    with pytest.raises(CarbonError, match="exceeds high bound"):
        load_carbon(bad2)

    with pytest.raises(CarbonError, match="not found"):
        load_carbon(tmp_path / "missing.yaml")
