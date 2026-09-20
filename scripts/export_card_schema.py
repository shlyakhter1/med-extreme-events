"""Write cards/card.schema.json from the Pydantic Card model. Run via `make schema`."""

from __future__ import annotations

import sys

from xevents.cards import SCHEMA_PATH, card_json_schema_text


def main() -> int:
    SCHEMA_PATH.write_text(card_json_schema_text(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
