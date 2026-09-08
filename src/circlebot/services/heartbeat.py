"""Liveness beat for the container healthcheck.

Every ``interval`` seconds the loop runs a cheap ``SELECT 1`` and then touches the
heartbeat file. Pairing the query with the touch is what makes the signal worth
having: it proves the event loop is still scheduling *and* that Postgres is
reachable -- which is exactly what a wedged-but-running bot fails to do while still
looking "up" to Docker.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..health import touch

log = logging.getLogger(__name__)


async def ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def heartbeat_loop(engine: AsyncEngine, path: Path, interval: float) -> None:
    while True:
        try:
            await ping_db(engine)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # WARNING so this also reaches the Telegram alerts; the stale heartbeat
            # will independently flip the container to unhealthy.
            log.warning("heartbeat: database unreachable: %s", exc)
        else:
            try:
                touch(path)
            except OSError as exc:
                log.warning("heartbeat: cannot write %s: %s", path, exc)
        await asyncio.sleep(interval)
