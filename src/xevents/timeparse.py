"""Forgiving ISO-8601 parsing for ``at=`` parameters.

A browser form submits ``2026-09-20T11:42:21+00:00`` as ``...21 00:00`` because ``+`` is the
URL encoding for a space, so a naive ``fromisoformat`` rejects what the page itself produced.
We accept that form, a trailing ``Z``, a bare date, and ``datetime-local`` minute precision.
Naive values are read as UTC; offset values are converted to UTC.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

_SPACE_OFFSET = re.compile(r"(?<=\d)\s(\d{2}:\d{2})$")


class BadTimestamp(ValueError):
    pass


def parse_at(value: str | None) -> datetime | None:
    """``None``/empty → None. Raises ``BadTimestamp`` with the original text."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    candidate = _SPACE_OFFSET.sub(r"+\1", text).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
        else:
            raise BadTimestamp(f"bad timestamp {value!r}") from None
    # Always hand back UTC: the SQLite fallback compares stored timestamps as wall-clock
    # text, so an offset left on the value would shift every active-at query by that offset.
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def to_input_value(dt: datetime) -> str:
    """Minute precision for ``<input type=datetime-local>`` (no offset, so no ``+``)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")
