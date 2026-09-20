"""Link a curated subset of data-source skills from the sibling skills repo into .claude/skills.

The skills stay in their home repo (default ``../../nyc2026-dataset``, a sibling of
``medtask/``); this only creates relative symlinks so Claude Code can discover them as
project skills. Run via ``make skills`` (create/refresh) or ``make skills-check`` (verify,
exit 1 on problems).

Environment: ``SKILLS_REPO`` overrides the path to the skills repo.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
DEFAULT_SKILLS_REPO = Path(os.environ.get("SKILLS_REPO", "../../nyc2026-dataset"))
SKILLS_SUBDIR = Path(".agents/skills")  # canonical location in nyc2026-dataset

# Curated for this project: one line per skill, with the milestone that needs it.
LINKED_SKILLS: dict[str, str] = {
    "search-va-facilities-api": "M1 facility spine (Lighthouse Facilities API)",
    "search-epa-airnow-aqs": "M2 AirNow provider (consolidated endpoints, 500 req/h)",
    "search-cdc-places": "M3 denominators (PLACES county measures via Socrata)",
    "search-cdc-heat-medications-guidance": "Cards 1/2/4 source; cached med-class list",
    "search-noaa-ncei-daily-summaries": "M2 fixture builders (temperature context)",
    "search-system-climate-research": "Evidence enrichment (effect sizes with CI/DOI)",
    "search-harvard-dataverse-graph-snapshot": "Evidence enrichment (scientific findings graph)",
}


def resolve_repo(skills_repo: Path) -> Path:
    return skills_repo if skills_repo.is_absolute() else (REPO_ROOT / skills_repo).resolve()


def link(skills_repo: Path, *, check_only: bool) -> int:
    repo = resolve_repo(skills_repo)
    source_root = repo / SKILLS_SUBDIR
    if not source_root.is_dir():
        print(f"skills repo not found: {source_root} (set SKILLS_REPO=<path>)", file=sys.stderr)
        return 1
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    problems = 0
    for name, purpose in LINKED_SKILLS.items():
        target = source_root / name
        dest = SKILLS_DIR / name
        rel = Path(os.path.relpath(target, SKILLS_DIR))
        if not (target / "SKILL.md").is_file():
            print(f"MISSING  {name}: no SKILL.md at {target}", file=sys.stderr)
            problems += 1
            continue
        if dest.is_symlink() and dest.resolve() == target.resolve():
            print(f"ok       {name} -> {rel}  ({purpose})")
            continue
        if check_only:
            state = "dangling" if dest.is_symlink() else ("exists" if dest.exists() else "absent")
            print(f"BAD      {name}: {state}, expected symlink -> {rel}", file=sys.stderr)
            problems += 1
            continue
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            print(f"REFUSING {name}: {dest} is a real directory, not a symlink", file=sys.stderr)
            problems += 1
            continue
        dest.symlink_to(rel, target_is_directory=True)
        print(f"linked   {name} -> {rel}  ({purpose})")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only; do not modify")
    parser.add_argument("--skills-repo", type=Path, default=DEFAULT_SKILLS_REPO)
    args = parser.parse_args()
    return link(args.skills_repo, check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
