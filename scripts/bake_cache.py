"""Write the response-cache snapshot a container loads at startup (``CACHE_SNAPSHOT``).

Run at image build time, after ingest and match, against the database baked into the image:
replay responses, Scenarios/Cards stats, scenario summaries and boundary files are all fixed
by then, so computing them here spares every new instance the work. On the free hosted
instance that work took minutes after each wake from sleep, and pages waited behind it.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from xevents.api import bake_snapshot
from xevents.store import make_engine


def main() -> int:
    target = os.environ.get("CACHE_SNAPSHOT")
    if not target:
        print("CACHE_SNAPSHOT is not set", file=sys.stderr)
        return 2
    path = Path(target)
    started = time.monotonic()
    n = bake_snapshot(make_engine(), path)
    size = path.stat().st_size / 1e6
    print(
        f"cache snapshot: {n} entries, {size:.1f} MB → {path} in {time.monotonic() - started:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
