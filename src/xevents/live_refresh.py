"""Background live refresh for a hosted demo.

Live events live only in the running instance's database: a rebuilt container, a Render
redeploy or a free instance waking from sleep starts from the image, which holds the replay
scenarios and nothing live. With ``LIVE_REFRESH_MINUTES`` > 0 the web app runs live ingest
and live match at startup (after a short delay) and then every N minutes, so the live view
repopulates itself. Each step runs as a subprocess — the same ``scripts/ingest.py`` and
``scripts/match.py`` an operator would run — which keeps provider network code out of the
web process and returns its memory to the OS after every run. Output goes to stdout so it
appears in the host's logs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STEPS: list[tuple[str, list[str]]] = [
    ("ingest.py", ["--mode", "live"]),
    ("match.py", ["--mode", "live"]),
]


def minutes_from_env(env: dict[str, str] | None = None) -> float:
    """``LIVE_REFRESH_MINUTES`` as a positive number, else 0 (disabled)."""
    raw = (env if env is not None else os.environ).get("LIVE_REFRESH_MINUTES", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        print(f"live refresh: ignoring LIVE_REFRESH_MINUTES={raw!r} (not a number)", flush=True)
        return 0.0
    return value if value > 0 else 0.0


# The refresh shares a small hosted CPU with the web process; run it at lower priority so page
# requests are served first while an hourly ingest is running.
_NICE = ["nice", "-n", "10"] if shutil.which("nice") else []


def refresh_once(timeout_s: float = 900.0) -> bool:
    """Run live ingest then live match. False if a step failed (ingest fails only when every
    provider failed; the per-provider lines say which)."""
    env = {**os.environ, "EVENT_MODE": "live"}
    for script, args in STEPS:
        started = time.monotonic()
        result = subprocess.run(
            [*_NICE, sys.executable, str(REPO_ROOT / "scripts" / script), *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        for line in (result.stdout + result.stderr).splitlines():
            print(f"live refresh {script}: {line}", flush=True)
        took = time.monotonic() - started
        if result.returncode != 0:
            print(f"live refresh {script}: exit {result.returncode} after {took:.0f}s", flush=True)
            return False
        print(f"live refresh {script}: ok in {took:.0f}s", flush=True)
    return True


def start(every_minutes: float, first_delay_s: float = 5.0) -> threading.Thread:
    """Daemon thread: refresh after ``first_delay_s``, then every ``every_minutes``."""

    def loop() -> None:
        time.sleep(first_delay_s)
        while True:
            try:
                refresh_once()
            except Exception as exc:  # a timeout or a crash must not kill the loop
                print(f"live refresh: failed: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(every_minutes * 60)

    thread = threading.Thread(target=loop, name="live-refresh", daemon=True)
    thread.start()
    print(
        f"live refresh: every {every_minutes:g} min (first run in {first_delay_s:g}s)", flush=True
    )
    return thread
