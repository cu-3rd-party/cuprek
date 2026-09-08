from circlebot.config import Settings, _parse_int_set


def _mk(**over: object) -> Settings:
    base: dict[str, object] = {
        "bot_token": "x",
        "database_url": "postgresql+asyncpg://u:p@h/db",
        "mod_chat_id": -100,
        "_env_file": None,
    }
    return Settings(**{**base, **over})  # type: ignore[arg-type]


def test_guaranteed_ids_parsed_from_csv() -> None:
    assert _mk(guaranteed_circle_ids="111, 222 333").guaranteed_circle_ids == {111, 222, 333}


def test_guaranteed_ids_default_empty() -> None:
    assert _mk().guaranteed_circle_ids == set()


def test_parse_int_set_forms() -> None:
    assert _parse_int_set("1,2, 3") == {1, 2, 3}
    assert _parse_int_set("") == set()
    assert _parse_int_set(None) == set()
    assert _parse_int_set([1, "2"]) == {1, 2}
