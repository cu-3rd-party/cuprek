"""The tracker only has to do one thing: count profane messages that still fall
inside a sliding window, cheaply. These pin the window boundary and the memory
bound.
"""
from __future__ import annotations

from circlebot.services.spam import RapidProfanityTracker


def test_running_count_below_threshold() -> None:
    t = RapidProfanityTracker()
    key = ("chat", 1)
    assert [t.hit(key, 60, now=n) for n in (0, 1, 2)] == [1, 2, 3]


def test_users_exact_scenario() -> None:
    # hits at 0s, 30s, 40s; a 4th at 60s -> the 0s hit has just left the window,
    # so the count is 3, not 4.
    t = RapidProfanityTracker()
    key = ("chat", 1)
    assert t.hit(key, 60, now=0) == 1
    assert t.hit(key, 60, now=30) == 2
    assert t.hit(key, 60, now=40) == 3
    assert t.hit(key, 60, now=60) == 3


def test_boundary_just_inside_window() -> None:
    t = RapidProfanityTracker()
    key = ("chat", 1)
    t.hit(key, 60, now=0)
    assert t.hit(key, 60, now=59.999) == 2


def test_old_timestamps_are_pruned() -> None:
    t = RapidProfanityTracker()
    key = ("chat", 1)
    t.hit(key, 60, now=0)
    assert t.hit(key, 60, now=100) == 1


def test_keys_are_independent() -> None:
    t = RapidProfanityTracker()
    a, b = ("chat", 1), ("chat", 2)
    assert t.hit(a, 60, now=0) == 1
    assert t.hit(b, 60, now=1) == 1
    assert t.hit(a, 60, now=2) == 2
    assert t.hit(b, 60, now=3) == 2


def test_window_shrink_at_runtime_prunes_harder() -> None:
    t = RapidProfanityTracker()
    key = ("chat", 1)
    for n in (0, 5, 10, 15):
        t.hit(key, 60, now=n)
    # window drops to 10s at now=20: only hits newer than 10s ago survive, i.e.
    # strictly after t=10 (>= boundary) -> {15, 20}.
    assert t.hit(key, 10, now=20) == 2


def test_default_clock_is_monotonic() -> None:
    t = RapidProfanityTracker()
    assert t.hit("k", 60) == 1
    assert t.hit("k", 60) == 2


def test_bucket_dict_is_swept_when_it_exceeds_max_keys() -> None:
    t = RapidProfanityTracker(max_keys=4)
    for k in range(4):
        t.hit(k, 10, now=0)
    # 5th key at now=100: dict is over the cap, the four stale keys are dropped.
    assert t.hit(99, 10, now=100) == 1
    assert set(t._buckets) == {99}
