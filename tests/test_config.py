from circlebot.config import Settings, parse_int_set


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
    assert parse_int_set("1,2, 3") == {1, 2, 3}
    assert parse_int_set("") == set()
    assert parse_int_set(None) == set()
    assert parse_int_set([1, "2"]) == {1, 2}


def test_profanity_knobs_read_from_env() -> None:
    s = _mk(
        profanity_free_messages="5",
        profanity_base_chance="2.5",
        profanity_step="1.0",
    )
    assert s.profanity_free_messages == 5
    assert s.profanity_base_chance == 2.5
    assert s.profanity_step == 1.0


def test_profanity_spam_knobs_read_from_env() -> None:
    s = _mk(profanity_spam_messages="5", profanity_spam_window="120")
    assert s.profanity_spam_messages == 5
    assert s.profanity_spam_window == 120


def test_profanity_spam_knobs_default() -> None:
    s = _mk()
    assert (s.profanity_spam_messages, s.profanity_spam_window) == (3, 60)
