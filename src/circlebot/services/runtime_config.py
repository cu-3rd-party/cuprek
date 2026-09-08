"""Admin-tunable knobs for the profanity -> circle chance curve.

Each knob has a ``PROFANITY_*`` default in ``.env`` (frozen into ``Settings`` at
startup) and an optional override row in ``bot_settings`` that the ``/config``
command writes. The override wins while it exists; ``/config reset`` drops it and
the ``.env`` value takes over again.

This module is pure -- no DB, no aiogram -- so the merge and the input validation
are unit-testable on their own.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .chance import circle_chance


@dataclass(frozen=True)
class Knob:
    key: str  # bot_settings row key AND the matching Settings attribute name
    field: str  # the ProfanityConfig field it fills
    kind: type  # int or float -- the stored float is cast through this
    minimum: float
    maximum: float
    label: str  # human name, shown by /config and in errors
    unit: str  # "" or "%"


# Keyed by the alias an admin types: ``/config chance 2.0``.
KNOBS: dict[str, Knob] = {
    "chance": Knob("profanity_base_chance", "base_chance", float, 0.0, 100.0, "базовый шанс", "%"),
    "free": Knob(
        "profanity_free_messages", "free_messages", int, 0, 1000, "бесплатные сообщения", ""
    ),
    "step": Knob("profanity_step", "step", float, 0.0, 100.0, "шаг", "%"),
}


@dataclass(frozen=True)
class ProfanityConfig:
    free_messages: int
    base_chance: float
    step: float


def resolve_profanity_config(
    overrides: dict[str, float], settings: Settings
) -> ProfanityConfig:
    """Merge ``bot_settings`` rows over the ``.env`` defaults. Unknown keys in
    ``overrides`` (e.g. a knob removed in a later version) are ignored.
    """
    values: dict[str, object] = {}
    for knob in KNOBS.values():
        raw = overrides.get(knob.key)
        values[knob.field] = knob.kind(raw if raw is not None else getattr(settings, knob.key))
    return ProfanityConfig(**values)  # type: ignore[arg-type]


def parse_knob_value(alias: str, raw: str) -> float:
    """Validate an admin-supplied value for knob ``alias``.

    Returns the number to store -- always a float, because that is the
    ``bot_settings.value`` column type. Raises ``ValueError`` with a message safe
    to show the admin verbatim.
    """
    knob = KNOBS[alias]
    try:
        number = float(raw.replace(",", "."))
    except ValueError:
        raise ValueError(f"«{raw}» — это не число") from None
    if knob.kind is int and not number.is_integer():
        raise ValueError(f"{knob.label}: нужно целое число")
    if not (knob.minimum <= number <= knob.maximum):
        raise ValueError(
            f"{knob.label}: допустимо от {knob.minimum:g} до {knob.maximum:g}"
        )
    return number


def _fmt(knob: Knob, value: float) -> str:
    body = f"{int(value)}" if knob.kind is int else f"{value:g}"
    return body + knob.unit


def render_config(overrides: dict[str, float], settings: Settings) -> str:
    """The text ``/config`` shows: every knob's effective value, its default, an
    "изменено" marker when overridden, and a worked example of the resulting curve.
    """
    cfg = resolve_profanity_config(overrides, settings)
    lines = ["⚙️ <b>Кривая мат → кружок</b>", ""]
    for alias, knob in KNOBS.items():
        current = _fmt(knob, getattr(cfg, knob.field))
        default = _fmt(knob, getattr(settings, knob.key))
        mark = "  ← изменено" if knob.key in overrides else ""
        lines.append(f"<code>{alias}</code> — {current} (дефолт {default}){mark}")

    free = cfg.free_messages

    def roll(n: int) -> float:
        return circle_chance(
            n, free_messages=free, base_chance=cfg.base_chance, step=cfg.step
        ) * 100

    lines += [
        "",
        f"{free + 1}-е матное сообщение за день: {roll(free + 1):g}% · "
        f"{free + 2}-е: {roll(free + 2):g}%",
        "",
        "Изменить: <code>/config chance 2.0</code> · "
        "сброс: <code>/config reset [chance|free|step]</code>",
    ]
    return "\n".join(lines)
