"""SIGTERM has to arrive as an event, not as a process kill.

That is what makes `docker compose restart` log a clean shutdown rather than look
like a crash in the logs, and what gives the bot session and DB engine a chance to
close. Polling itself needs a live token, so this covers the signal wiring directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import pytest

from circlebot.__main__ import _install_signal_handlers

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="loop.add_signal_handler is POSIX-only"
)


async def test_sigterm_requests_a_clean_shutdown(caplog: pytest.LogCaptureFixture) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    with caplog.at_level(logging.INFO):
        _install_signal_handlers(stop)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.wait_for(stop.wait(), timeout=2)
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)

    assert stop.is_set()
    assert any("shutting down" in r.getMessage() for r in caplog.records)


def test_install_is_a_no_op_where_signals_are_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows dev boxes must not crash on startup just because signals differ."""

    class NoSignalLoop:
        def add_signal_handler(self, *_args: object) -> None:
            raise NotImplementedError

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: NoSignalLoop())
    _install_signal_handlers(asyncio.Event())  # must not raise
