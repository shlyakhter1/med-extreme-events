"""Regenerate the card-facts block in docs/card-reference-for-frontend.md from cards/*.yaml.
Run via `make card-docs`; `--check` exits 1 if the block is stale."""

from __future__ import annotations

import sys

from xevents.cards import FRONTEND_REFERENCE_PATH, load_cards, render_frontend_reference


def main() -> int:
    doc = FRONTEND_REFERENCE_PATH.read_text(encoding="utf-8")
    fresh = render_frontend_reference(doc, load_cards())
    if "--check" in sys.argv[1:]:
        if fresh != doc:
            print(f"{FRONTEND_REFERENCE_PATH} is stale — run `make card-docs`")
            return 1
        return 0
    FRONTEND_REFERENCE_PATH.write_text(fresh, encoding="utf-8")
    print(f"wrote {FRONTEND_REFERENCE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
