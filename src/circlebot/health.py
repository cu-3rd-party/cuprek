"""Container healthcheck: ``python -m circlebot.health``.

Exits 0 while the bot's heartbeat file is fresh and 1 otherwise, which is what lets
``docker compose ps`` tell a running bot apart from a wedged one.

This module deliberately reads the environment directly instead of going through
``config.Settings``, and imports nothing heavy: the healthcheck has to work even when
the configuration is incomplete, and it runs every few seconds.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

DEFAULT_FILE = "/tmp/circlebot.heartbeat"
DEFAULT_MAX_AGE = 120.0


def touch(path: Path) -> None:
    """Record a beat. The content is for humans; the healthcheck reads the mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{time.time():.0f}\n", encoding="utf-8")


def age_seconds(path: Path) -> float | None:
    """Seconds since the last beat, or None if the file is missing/unreadable."""
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def is_fresh(path: Path, max_age: float) -> bool:
    age = age_seconds(path)
    return age is not None and age <= max_age


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def main() -> int:
    path = Path(os.environ.get("HEARTBEAT_FILE") or DEFAULT_FILE)
    max_age = _env_float("HEARTBEAT_MAX_AGE", DEFAULT_MAX_AGE)

    age = age_seconds(path)
    if age is None:
        print(f"unhealthy: no heartbeat at {path}", file=sys.stderr)
        return 1
    if age > max_age:
        print(f"unhealthy: heartbeat is {age:.0f}s old (max {max_age:.0f}s)", file=sys.stderr)
        return 1
    print(f"ok: heartbeat {age:.0f}s old")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
