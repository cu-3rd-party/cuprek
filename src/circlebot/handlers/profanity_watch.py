from __future__ import annotations

import logging
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import repo
from ..services.access import IdRegistry
from ..services.chance import circle_chance
from ..services.locks import KeyedLock
from ..services.profanity import ProfanityDetector
from ..services.runtime_config import resolve_profanity_config

router = Router(name="profanity_watch")
log = logging.getLogger(__name__)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def watch(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    detector: ProfanityDetector,
    locks: KeyedLock,
    registry: IdRegistry,
) -> None:
    if settings.allowed_chat_ids and message.chat.id not in settings.allowed_chat_ids:
        return
    user = message.from_user
    if user is None or user.is_bot or message.sender_chat is not None:
        return

    text = message.text or message.caption
    match = detector.find_match(text)
    if match is None:
        return

    chat_id, user_id = message.chat.id, user.id
    guaranteed = registry.is_guaranteed(user_id)
    day = datetime.now(ZoneInfo(settings.timezone)).date()

    async with locks((chat_id, user_id)):
        activity = await repo.get_daily_activity(session, chat_id, user_id, day)
        if not guaranteed and activity is not None and activity.circle_sent:
            return  # non-guaranteed user already got today's circle in this chat

        activity = await repo.increment_profane_count(session, chat_id, user_id, day)
        await session.commit()
        count = activity.profane_count

        cfg = resolve_profanity_config(await repo.get_bot_settings(session), settings)
        chance = circle_chance(
            count,
            free_messages=cfg.free_messages,
            base_chance=cfg.base_chance,
            step=cfg.step,
        )
        if not guaranteed and (chance <= 0.0 or random.random() >= chance):
            log.debug(
                "no circle: chat=%s user=%s count=%s chance=%.3f match=%r",
                chat_id, user_id, count, chance, match,
            )
            return

        circle = await repo.pick_random_active_circle(session)
        if circle is None:
            log.warning("profanity matched but the circle pool is empty")
            return

        # Send first, then claim the daily slot: the per-(chat, user) lock rules
        # out concurrent sends, so a failed send should not burn the user's circle.
        try:
            await message.reply_video_note(circle.file_id)
        except TelegramAPIError:
            log.exception("failed to send circle=%s to chat=%s", circle.id, chat_id)
            return

        await repo.mark_circle_sent(session, chat_id, user_id, day, circle.id)
        await session.commit()
        log.info(
            "circle=%s sent chat=%s user=%s count=%s chance=%.3f guaranteed=%s",
            circle.id, chat_id, user_id, count, chance, guaranteed,
        )
