import pytest

from circlebot.config import Settings
from circlebot.services.runtime_config import (
    parse_knob_value,
    render_config,
    resolve_profanity_config,
)


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "bot_token": "x",
        "database_url": "postgresql+asyncpg://u:p@h/db",
        "mod_chat_id": -100,
        "_env_file": None,
    }
    return Settings(**{**base, **over})  # type: ignore[arg-type]


def test_resolve_defaults_to_env_values() -> None:
    cfg = resolve_profanity_config({}, _settings())
    assert (cfg.free_messages, cfg.base_chance, cfg.step) == (3, 1.0, 0.5)
    assert isinstance(cfg.free_messages, int)
    assert isinstance(cfg.base_chance, float)


def test_resolve_uses_non_default_env_when_no_override() -> None:
    cfg = resolve_profanity_config(
        {},
        _settings(profanity_free_messages=5, profanity_base_chance=2.0, profanity_step=1.5),
    )
    assert (cfg.free_messages, cfg.base_chance, cfg.step) == (5, 2.0, 1.5)


def test_resolve_partial_db_override_leaves_the_rest_alone() -> None:
    cfg = resolve_profanity_config({"profanity_base_chance": 2.0}, _settings())
    assert cfg.base_chance == 2.0
    assert (cfg.free_messages, cfg.step) == (3, 0.5)


def test_resolve_full_override_casts_free_to_int() -> None:
    cfg = resolve_profanity_config(
        {
            "profanity_free_messages": 5.0,
            "profanity_base_chance": 4.0,
            "profanity_step": 2.0,
        },
        _settings(),
    )
    assert (cfg.free_messages, cfg.base_chance, cfg.step) == (5, 4.0, 2.0)
    assert isinstance(cfg.free_messages, int)


def test_resolve_ignores_unknown_keys() -> None:
    cfg = resolve_profanity_config({"profanity_retired_knob": 9.0}, _settings())
    assert cfg.free_messages == 3


@pytest.mark.parametrize(
    ("alias", "raw", "expected"),
    [
        ("chance", "2.5", 2.5),
        ("chance", "2,5", 2.5),  # RU decimal comma
        ("free", "5", 5.0),
        ("step", "0", 0.0),
        ("chance", "100", 100.0),
    ],
)
def test_parse_knob_value_accepts(alias: str, raw: str, expected: float) -> None:
    assert parse_knob_value(alias, raw) == expected


@pytest.mark.parametrize(
    ("alias", "raw"),
    [
        ("chance", "abc"),
        ("chance", "-1"),
        ("chance", "150"),
        ("free", "5.5"),
        ("free", "-2"),
        ("step", "999"),
    ],
)
def test_parse_knob_value_rejects(alias: str, raw: str) -> None:
    with pytest.raises(ValueError):
        parse_knob_value(alias, raw)


def test_render_flags_only_overridden_knobs() -> None:
    lines = render_config({"profanity_base_chance": 2.0}, _settings()).splitlines()
    chance_line = next(ln for ln in lines if ln.startswith("<code>chance</code>"))
    free_line = next(ln for ln in lines if ln.startswith("<code>free</code>"))
    assert "изменено" in chance_line
    assert "изменено" not in free_line


def test_render_sample_points_reflect_the_override() -> None:
    # base_chance -> 10 means the first "paid" (4th) message sits at 10%
    assert "10%" in render_config({"profanity_base_chance": 10.0}, _settings())
