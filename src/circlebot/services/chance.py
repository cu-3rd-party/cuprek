from __future__ import annotations


def circle_chance(
    profane_count: int,
    *,
    free_messages: int = 3,
    base_chance: float = 1.0,
    step: float = 0.5,
) -> float:
    """Probability in ``[0.0, 1.0]`` of sending a circle for the given daily count.

    * ``profane_count <= free_messages`` -> ``0.0`` (nothing happens)
    * first "paid" message (``free_messages + 1``) -> ``base_chance`` percent
    * every message beyond that -> ``+ step`` percent, capped at 100 percent

    With the defaults: 4th profane message = 1%, 5th = 1.5%, ... 202nd = 100%.
    """
    if profane_count <= free_messages:
        return 0.0
    first_paid = free_messages + 1
    percent = base_chance + (profane_count - first_paid) * step
    percent = max(0.0, min(percent, 100.0))
    return percent / 100.0
