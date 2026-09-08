from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path

import pytest

from circlebot import health
from circlebot.services import heartbeat


def test_touch_then_fresh(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    health.touch(path)
    assert path.exists()
    assert health.age_seconds(path) < 1.0
    assert health.is_fresh(path, max_age=60)


def test_missing_file_is_not_fresh(tmp_path: Path) -> None:
    path = tmp_path / "never-written"
    assert health.age_seconds(path) is None
    assert not health.is_fresh(path, max_age=60)


def test_stale_file_is_not_fresh(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    health.touch(path)
    old = time.time() - 300
    os.utime(path, (old, old))
    assert not health.is_fresh(path, max_age=120)
    assert health.is_fresh(path, max_age=600)


@pytest.mark.parametrize(
    ("age_offset", "expected"),
    [(0, 0), (-300, 1)],
    ids=["fresh", "stale"],
)
def test_health_cli_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, age_offset: int, expected: int
) -> None:
    path = tmp_path / "beat"
    health.touch(path)
    if age_offset:
        stamp = time.time() + age_offset
        os.utime(path, (stamp, stamp))
    monkeypatch.setenv("HEARTBEAT_FILE", str(path))
    monkeypatch.setenv("HEARTBEAT_MAX_AGE", "120")
    assert health.main() == expected


def test_health_cli_reports_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "absent"))
    assert health.main() == 1


async def _run_briefly(coro: object) -> None:
    task = asyncio.create_task(coro)  # type: ignore[arg-type]
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_loop_beats_after_a_successful_ping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ok(_engine: object) -> None:
        return None

    monkeypatch.setattr(heartbeat, "ping_db", ok)
    path = tmp_path / "beat"
    await _run_briefly(heartbeat.heartbeat_loop(None, path, 0.01))  # type: ignore[arg-type]
    assert health.is_fresh(path, max_age=5)


async def test_loop_withholds_the_beat_when_the_database_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def boom(_engine: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(heartbeat, "ping_db", boom)
    path = tmp_path / "beat"
    with caplog.at_level(logging.WARNING):
        await _run_briefly(heartbeat.heartbeat_loop(None, path, 0.01))  # type: ignore[arg-type]

    # No beat -> the container healthcheck goes unhealthy, and the WARNING is what
    # reaches the Telegram alerts.
    assert not path.exists()
    assert any("database unreachable" in r.message for r in caplog.records)
