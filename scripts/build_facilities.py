"""Pull all VA health facilities (Facilities API v1) into fixtures/reference/facilities.geojson.

Requires ``VA_FACILITIES_API_KEY``. Self-service keys from developer.va.gov are sandbox
keys: production returns 401 until separate access is granted, so on a production 401 the
pull retries against ``sandbox-api.va.gov`` (same facility dataset). Raw JSON:API pages are
saved under ``fixtures/reference/raw/`` so the pull is auditable and rebuildable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from xevents.providers.va_facilities import (
    PRODUCTION_BASE_URL,
    SANDBOX_BASE_URL,
    FacilitiesAPIError,
    VAFacilitiesClient,
    to_geojson,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "fixtures" / "reference"
OUT = REFERENCE_DIR / "facilities.geojson"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", action="store_true", help="use sandbox-api.va.gov")
    parser.add_argument("--per-page", type=int, default=500)
    args = parser.parse_args()
    bases = [SANDBOX_BASE_URL] if args.sandbox else [PRODUCTION_BASE_URL, SANDBOX_BASE_URL]
    facilities = None
    base = bases[0]
    for base in bases:
        try:
            client = VAFacilitiesClient(base_url=base, per_page=args.per_page)
        except FacilitiesAPIError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        try:
            facilities = client.fetch_all("health", raw_dir=REFERENCE_DIR / "raw")
            break
        except FacilitiesAPIError as exc:
            if "HTTP 401" in str(exc) and base != bases[-1]:
                print(f"{base}: 401 (sandbox key?) — retrying against sandbox", file=sys.stderr)
                continue
            print(str(exc), file=sys.stderr)
            return 1
        finally:
            client.close()
    assert facilities is not None
    doc = to_geojson(facilities)
    doc["provenance"] = {
        "source": f"{base}/facilities?type=health",
        "retrieved": datetime.now(UTC).isoformat(timespec="seconds"),
        "count": len(facilities),
        "builder": "scripts/build_facilities.py",
    }
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(facilities)} health facilities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
