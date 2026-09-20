"""Card library loader: YAML files → validated ``Card`` models.

Rejects, with a file-anchored message, any card that fails the schema: unknown fields,
untiered claims, unknown source ids, duplicate ids, or a medication card without the
do-not-stop safety flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from xevents.models import Card

CARDS_DIR = Path(__file__).resolve().parents[2] / "cards"
SCHEMA_PATH = CARDS_DIR / "card.schema.json"


class CardValidationError(ValueError):
    """A card file failed validation. ``path`` is the offending file."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def _format_validation_error(err: ValidationError) -> str:
    lines = [f"{err.error_count()} validation error(s)"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "<root>"
        lines.append(f"  - {loc}: {e['msg']}")
    return "\n".join(lines)


def load_card(path: Path) -> Card:
    """Parse and validate one card file."""
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CardValidationError(path, f"YAML parse error: {exc}") from exc
    if not isinstance(raw, dict):
        raise CardValidationError(path, "top level must be a mapping")
    try:
        return Card.model_validate(raw)
    except ValidationError as exc:
        raise CardValidationError(path, _format_validation_error(exc)) from exc


def load_cards(directory: Path = CARDS_DIR) -> list[Card]:
    """Load every ``*.yaml`` card in ``directory`` (sorted by filename).

    Raises ``CardValidationError`` on the first bad file, and on duplicate card ids or
    numbers across files.
    """
    cards: list[Card] = []
    seen_ids: dict[str, Path] = {}
    seen_numbers: dict[int, Path] = {}
    for path in sorted(directory.glob("*.yaml")):
        card = load_card(path)
        if card.id in seen_ids:
            raise CardValidationError(
                path, f"duplicate card id '{card.id}' (also in {seen_ids[card.id]})"
            )
        if card.number in seen_numbers:
            raise CardValidationError(
                path, f"duplicate card number {card.number} (also in {seen_numbers[card.number]})"
            )
        seen_ids[card.id] = path
        seen_numbers[card.number] = path
        cards.append(card)
    return cards


def card_json_schema() -> dict[str, Any]:
    """JSON Schema for a card, derived from the Pydantic model (the source of truth)."""
    schema = Card.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://github.com/shlyakhter1/med-extreme-events/cards/card.schema.json"
    schema["title"] = "VA extreme-event playbook card"
    return schema


def card_json_schema_text() -> str:
    return json.dumps(card_json_schema(), indent=2, sort_keys=False) + "\n"
