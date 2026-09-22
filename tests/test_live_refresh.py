"""Live refresh (hosted demo): configuration, the two subprocess steps, failure handling,
SQLite WAL, and that the app never starts it unless asked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from xevents import live_refresh
from xevents.store import init_db, make_engine


def test_minutes_from_env() -> None:
    assert live_refresh.minutes_from_env({}) == 0
    assert live_refresh.minutes_from_env({"LIVE_REFRESH_MINUTES": ""}) == 0
    assert live_refresh.minutes_from_env({"LIVE_REFRESH_MINUTES": "60"}) == 60
    assert live_refresh.minutes_from_env({"LIVE_REFRESH_MINUTES": "0"}) == 0
    assert live_refresh.minutes_from_env({"LIVE_REFRESH_MINUTES": "-5"}) == 0
    assert live_refresh.minutes_from_env({"LIVE_REFRESH_MINUTES": "soon"}) == 0


def test_refresh_runs_ingest_then_match_in_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kw["env"]))
        return subprocess.CompletedProcess(cmd, 0, stdout="hms: 6 events\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert live_refresh.refresh_once() is True
    scripts = [Path(c[0][1]).name for c in calls]
    assert scripts == ["ingest.py", "match.py"]
    assert all(c[0][2:] == ["--mode", "live"] for c in calls)
    assert all(c[1]["EVENT_MODE"] == "live" for c in calls)


def test_refresh_stops_when_ingest_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(Path(cmd[1]).name)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="all providers failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert live_refresh.refresh_once() is False
    assert calls == ["ingest.py"], "no match after a failed ingest"


def test_app_does_not_start_refresh_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from xevents.api import create_app

    started: list[float] = []
    monkeypatch.setattr(live_refresh, "start", lambda minutes, **kw: started.append(minutes))
    monkeypatch.delenv("LIVE_REFRESH_MINUTES", raising=False)
    with TestClient(create_app(make_engine("sqlite://"))):
        pass
    assert started == []
    monkeypatch.setenv("LIVE_REFRESH_MINUTES", "30")
    with TestClient(create_app(make_engine("sqlite://"))):
        pass
    assert started == [30.0]


def test_sqlite_uses_wal_so_reads_do_not_block_on_refresh(tmp_path: Path) -> None:
    eng = make_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    init_db(eng)
    with eng.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 10000


def test_image_and_blueprint_enable_refresh() -> None:
    root = Path(__file__).parents[1]
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "LIVE_REFRESH_MINUTES=60" in docker and "NWS_USER_AGENT=" in docker
    import yaml

    svc = yaml.safe_load((root / "render.yaml").read_text(encoding="utf-8"))["services"][0]
    env = {e["key"]: e["value"] for e in svc["envVars"]}
    assert env["LIVE_REFRESH_MINUTES"] == "60" and "github.com" in env["NWS_USER_AGENT"]
