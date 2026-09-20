"""Guard: no committed file may carry a real credential.

A live VA Facilities API key reached a public repository through `.env.example` because a
commit guard matched `.env` exactly and `.env.example` is a different filename. These tests
check the content, not the filename.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Names whose value must never be committed with content.
SECRET_NAMES = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
# A bare assignment with a value that is not an obvious placeholder or a URL/DSN.
ASSIGNMENT = re.compile(r"^\s*(?!#)([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")
PLACEHOLDER = re.compile(
    r"^$|^[\"']{0,2}$|<.*>|your[-_ ]|example|changeme|xxx+|\.\.\.|placeholder", re.IGNORECASE
)


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line]


def test_env_example_has_no_values_for_secrets() -> None:
    """Every secret in the example file must be an empty assignment."""
    offenders = []
    for lineno, line in enumerate(ENV_EXAMPLE.read_text(encoding="utf-8").splitlines(), 1):
        m = ASSIGNMENT.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2).split("#")[0].strip()
        if SECRET_NAMES.search(name) and not PLACEHOLDER.match(value):
            offenders.append(f"{ENV_EXAMPLE.name}:{lineno} {name} has a value")
    assert not offenders, "\n".join(offenders)


def test_the_real_env_file_is_never_tracked() -> None:
    tracked = {p.name for p in _tracked_files()}
    assert ".env" not in tracked, ".env must stay untracked; it holds live credentials"


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in _tracked_files()
        if p.suffix in {".yaml", ".yml", ".toml", ".md", ".env", ""} or p.name.startswith(".env")
    ],
)
def test_no_tracked_file_assigns_a_secret(path: Path) -> None:
    """Catch a credential pasted into any tracked config or doc, not just .env.example."""
    if not path.is_file() or path.stat().st_size > 2_000_000:
        pytest.skip("not a small text file")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pytest.skip("binary")
    for lineno, line in enumerate(text.splitlines(), 1):
        m = ASSIGNMENT.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2).split("#")[0].strip().strip("\"'")
        if not SECRET_NAMES.search(name) or PLACEHOLDER.match(value):
            continue
        # a long opaque token is the shape we care about
        assert not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", value), (
            f"{path.relative_to(REPO_ROOT)}:{lineno} assigns a credential-shaped value to {name}"
        )
