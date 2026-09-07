from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager


class KeyedLock:
    """A family of ``asyncio.Lock``s addressed by an arbitrary hashable key.

    Used to fully serialise the "count -> roll -> send" flow per (chat, user)
    inside a single bot process. Idle locks are dropped once released so the
    dictionary does not grow without bound.
    """

    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._waiters: dict[Hashable, int] = {}

    @asynccontextmanager
    async def __call__(self, key: Hashable) -> AsyncIterator[None]:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        self._waiters[key] = self._waiters.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._waiters[key] -= 1
            if self._waiters[key] <= 0:
                self._waiters.pop(key, None)
                self._locks.pop(key, None)
