"""``/config`` -- let admins retune the profanity -> circle curve without a redeploy.

The three knobs (`chance`, `free`, `step`) have `.env` defaults; this command
writes per-knob overrides into ``bot_settings`` that take effect on the next
profane message and survive restarts. ``/config reset`` drops them again.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import repo
from ..services.access import IdRegistry
from ..services.runtime_config import KNOBS, parse_knob_value, render_config

router = Router(name="config")
log = logging.getLogger(__name__)

_USAGE = (
    "Параметры: " + ", ".join(f"<code>{alias}</code>" for alias in KNOBS) + "\n"
    "Изменить: <code>/config chance 2.0</code>\n"
    "Сбросить: <code>/config reset</code> или <code>/config reset step</code>"
)


@router.message(Command("config"), F.chat.type == "private")
async def cmd_config(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    registry: IdRegistry,
    command: CommandObject,
) -> None:
    user = message.from_user
    if user is None or not registry.is_admin(user.id):
        return

    args = (command.args or "").split()
    if not args:
        await message.answer(render_config(await repo.get_bot_settings(session), settings))
        return

    verb = args[0].lower()

    if verb == "reset":
        targets = [a.lower() for a in args[1:]] or list(KNOBS)
        unknown = [t for t in targets if t not in KNOBS]
        if unknown:
            await message.reply(f"Не знаю параметр: {', '.join(unknown)}\n\n{_USAGE}")
            return
        cleared = [t for t in targets if await repo.clear_bot_setting(session, KNOBS[t].key)]
        await session.commit()
        if not cleared:
            await message.reply("Всё и так на дефолтах.")
            return
        log.info("config reset %s by=%s", ",".join(cleared), user.id)
        await message.answer(
            "Сброшено в дефолт: " + ", ".join(cleared) + "\n\n"
            + render_config(await repo.get_bot_settings(session), settings)
        )
        return

    if verb not in KNOBS:
        await message.reply(f"Не знаю параметр «{verb}».\n\n{_USAGE}")
        return
    if len(args) < 2:
        await message.reply(f"Нужно значение: <code>/config {verb} 2.0</code>")
        return

    try:
        value = parse_knob_value(verb, args[1])
    except ValueError as exc:
        await message.reply(f"⚠️ {exc}")
        return

    await repo.set_bot_setting(session, KNOBS[verb].key, value, updated_by=user.id)
    await session.commit()
    log.info("config %s=%s by=%s", KNOBS[verb].key, value, user.id)
    await message.answer(render_config(await repo.get_bot_settings(session), settings))
