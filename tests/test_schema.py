"""cards/card.schema.json is generated from the Pydantic model and must stay in sync."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from tests.conftest import INVALID_CARDS
from xevents.cards import CARDS_DIR, SCHEMA_PATH, card_json_schema, card_json_schema_text


def test_checked_in_schema_matches_model() -> None:
    assert SCHEMA_PATH.exists(), "run `make schema`"
    assert SCHEMA_PATH.read_text(encoding="utf-8") == card_json_schema_text(), (
        "cards/card.schema.json is stale — run `make schema`"
    )


def test_schema_is_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(card_json_schema())


@pytest.mark.parametrize("path", sorted(CARDS_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_each_card_validates_against_json_schema(path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    jsonschema.validate(doc, schema, cls=jsonschema.Draft202012Validator)


def test_json_schema_rejects_untiered_claim() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = yaml.safe_load((INVALID_CARDS / "untiered-claim.yaml").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError, match="'tier' is a required property"):
        jsonschema.validate(doc, schema, cls=jsonschema.Draft202012Validator)


def test_json_schema_rejects_weak_tier() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = yaml.safe_load((INVALID_CARDS / "weak-tier.yaml").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError, match="'weak' is not one of"):
        jsonschema.validate(doc, schema, cls=jsonschema.Draft202012Validator)
