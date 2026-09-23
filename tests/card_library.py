"""Test helpers: the reviewed card library and the medical-references index, as the tests
read them. Test-only — `docs/` is not shipped in the image, so nothing at runtime parses it.
"""

from __future__ import annotations

import re
from functools import cache

from xevents.cards import CARDS_DIR

DOCS = CARDS_DIR.parent / "docs"
LIBRARY_PATH = DOCS / "card-library.md"
REFERENCES_PATH = DOCS / "medical-references.md"

SHARED_MARKER = "[SHARED]"
# Library markup stripped on transcription (docs/card-library.md header): **[SHARED]**, and
# claim markers such as "[strong | finley-1995]" or "[inferential | chen-2025 — … pending]".
_MARKUP = re.compile(
    r"\*{0,2}\[SHARED\]\*{0,2} ?|\[(?:strong|inferential|expert_guidance) \|[^\]]*\] ?"
)


def flat(text: str) -> str:
    """Whitespace-collapsed text, the form every verbatim comparison uses."""
    return re.sub(r"\s+", " ", text).strip()


@cache
def library_text() -> str:
    """The whole library with markup stripped and emphasis removed, whitespace-collapsed."""
    raw = LIBRARY_PATH.read_text(encoding="utf-8")
    return flat(_MARKUP.sub("", raw).replace("*", ""))


@cache
def reference_index() -> dict[str, str]:
    """Source id → status (``verified`` | ``pending``) from medical-references.md §1.

    A status cell counts as pending only when it starts with "pending"; "verified (OR 2.43);
    polypharmacy OR pending full text" is verified for the figures the card quotes. One row
    may list several ids (the VA prevalence anchors).
    """
    text = REFERENCES_PATH.read_text(encoding="utf-8")
    section = text.split("## 1.", 1)[1].split("## 2.", 1)[0]
    index: dict[str, str] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[0].startswith("`"):
            continue
        status = "pending" if cells[2].lower().startswith("pending") else "verified"
        for sid in re.findall(r"`([a-z0-9-]+)`", cells[0]):
            index[sid] = status
    return index


@cache
def sources_by_card() -> dict[int, set[str]]:
    """Card number → source ids, from the medical-references.md §2 table."""
    text = REFERENCES_PATH.read_text(encoding="utf-8")
    section = text.split("## 2.", 1)[1].split("## 3.", 1)[0]
    table: dict[int, set[str]] = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*(\d+)\s[^|]*\|([^|]*)\|", line)
        if m:
            table[int(m.group(1))] = {s.strip() for s in m.group(2).split(",") if s.strip()}
    return table
