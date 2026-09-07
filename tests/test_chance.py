from itertools import pairwise

import pytest

from circlebot.services.chance import circle_chance


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, 0.0),
        (1, 0.0),
        (2, 0.0),
        (3, 0.0),
        (4, 0.01),
        (5, 0.015),
        (6, 0.02),
        (10, 0.04),
        (24, 0.11),
    ],
)
def test_default_curve(count: int, expected: float) -> None:
    assert circle_chance(count) == pytest.approx(expected)


def test_capped_at_one() -> None:
    assert circle_chance(202) == 1.0
    assert circle_chance(500) == 1.0
    assert circle_chance(10_000) == 1.0


def test_custom_parameters() -> None:
    # nothing until the 6th message, then 2% + 1% per extra message
    assert circle_chance(5, free_messages=5) == 0.0
    assert circle_chance(6, free_messages=5, base_chance=2.0, step=1.0) == pytest.approx(0.02)
    assert circle_chance(9, free_messages=5, base_chance=2.0, step=1.0) == pytest.approx(0.05)


def test_monotonic_non_decreasing() -> None:
    values = [circle_chance(n) for n in range(400)]
    assert all(b >= a for a, b in pairwise(values))
