"""In-memory sliding-window counter of confirmed-profane messages per key.

The point is to answer "has this user sent N+ profane messages in the last W
seconds?" without persisting message history or querying the DB on the hot path.
Only messages the detector already flagged reach here, so the structure stays
tiny.

``hit`` is the whole API: it drops timestamps that have aged out of the window,
records ``now``, and returns how many are still inside it. Expiry is lazy -- a
key is only cleaned when that key is touched again -- with a cap-and-sweep as the
backstop so the dict cannot grow without bound. This mirrors the rate limiter in
``services.alerts`` (deque prune + dict cap-and-sweep).

Single-threaded asyncio: ``hit`` has no ``await`` inside, so the read-modify-check
is atomic between tasks and needs no lock. Callers run it inside the existing
per-(chat, user) ``KeyedLock`` anyway, which also serialises the reaction send.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Hashable

_MAX_KEYS = 2048  # bound the bucket dict; mirrors alerts._LAST_SEEN_CAP


class RapidProfanityTracker:
    """Per-key ring of recent profane-message timestamps."""

    def __init__(self, *, max_keys: int = _MAX_KEYS) -> None:
        self._buckets: dict[Hashable, deque[float]] = {}
        self._max_keys = max_keys

    def hit(self, key: Hashable, window: float, *, now: float | None = None) -> int:
        """Record a profane message for ``key`` and return how many fall within
        the last ``window`` seconds, including this one (so always >= 1).

        ``window`` is passed per call rather than stored so a runtime ``/config``
        change takes effect on the next message. ``now`` is injectable for tests;
        it defaults to ``time.monotonic()``.
        """
        now = time.monotonic() if now is None else now
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = deque()
        # A message exactly ``window`` seconds old has left the window (>=, not >).
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        bucket.append(now)
        if len(self._buckets) > self._max_keys:
            self._sweep(now, window)
        return len(bucket)

    def _sweep(self, now: float, window: float) -> None:
        """Drop every key whose most recent hit is already outside the window.

        The just-touched key survives (``now - now == 0 < window``). A transient
        overshoot above ``max_keys`` when many keys are active at once is
        accepted -- same posture as ``alerts``.
        """
        self._buckets = {
            k: b for k, b in self._buckets.items() if b and now - b[-1] < window
        }
