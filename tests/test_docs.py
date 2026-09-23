"""Docs that are derived from, or point at, the cards stay in step with them."""

from __future__ import annotations

import re
from pathlib import Path

from xevents.cards import FRONTEND_REFERENCE_PATH, load_cards, render_frontend_reference

REPO = FRONTEND_REFERENCE_PATH.parents[1]
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def test_frontend_card_facts_are_fresh() -> None:
    doc = FRONTEND_REFERENCE_PATH.read_text(encoding="utf-8")
    assert render_frontend_reference(doc, load_cards()) == doc, "run `make card-docs`"


def _docs() -> list[Path]:
    paths = [*sorted((REPO / "docs").rglob("*.md")), REPO / "README.md", REPO / "CLAUDE.md"]
    return [p for p in paths if "medical_review" not in p.parts]


def test_relative_doc_links_resolve() -> None:
    """Guide pages and plans link to each other; a merged or renamed doc (card-library-
    additions.md → card-library.md) must not leave a dead link behind."""
    dead = []
    for path in _docs():
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                dead.append(f"{path.relative_to(REPO)} → {target}")
    assert not dead, dead
