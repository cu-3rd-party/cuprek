from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_int_set(value: object) -> set[int]:
    if value is None or value == "":
        return set()
    if isinstance(value, (set, list, tuple)):
        return {int(v) for v in value}
    if isinstance(value, int):
        return {value}
    if isinstance(value, str):
        return {int(part) for part in value.replace(",", " ").split()}
    raise TypeError(f"cannot parse int set from {value!r}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str
    database_url: str

    admin_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)
    mod_chat_id: int
    allowed_chat_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)

    timezone: str = "Europe/Moscow"
    max_pending_per_user: int = 5
    admin_dm_auto_accept: bool = True

    profanity_free_messages: int = 3
    profanity_base_chance: float = 1.0
    profanity_step: float = 0.5

    drop_pending_updates: bool = True
    log_level: str = "INFO"

    # Directory with the profanity word/pattern lists. Relative paths are resolved
    # against the current working directory (repo root locally, /app in Docker).
    data_dir: str = "data"

    @field_validator("admin_ids", "allowed_chat_ids", mode="before")
    @classmethod
    def _coerce_int_set(cls, value: object) -> set[int]:
        return _parse_int_set(value)

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        return path if path.is_absolute() else (Path.cwd() / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values are supplied via env / .env
