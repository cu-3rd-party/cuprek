from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, ReplyParameters
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import repo
from ..keyboards import moderation_kb
from ..services.access import IdRegistry

router = Router(name="submissions")
log = logging.getLogger(__name__)


@router.message(F.chat.type == "private", F.video_note)
async def on_video_note(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    registry: IdRegistry,
) -> None:
    video_note = message.video_note
    user = message.from_user
    if video_note is None or user is None:
        return

    if await repo.circle_exists(session, video_note.file_unique_id):
        await message.reply("Такой кружок уже есть в базе 🙂")
        return
    if await repo.pending_submission_exists(session, video_note.file_unique_id):
        await message.reply("Такой кружок уже на модерации, дождись решения.")
        return

    is_admin = registry.is_admin(user.id)
    if is_admin and settings.admin_dm_auto_accept:
        await repo.add_circle(
            session,
            file_id=video_note.file_id,
            file_unique_id=video_note.file_unique_id,
            duration=video_note.duration,
            added_by=user.id,
            source="admin_dm",
        )
        await session.commit()
        total = await repo.count_active_circles(session)
        log.info("circle added directly by admin=%s, pool=%s", user.id, total)
        await message.reply(f"✅ Добавил в базу. Всего кружков: {hbold(total)}")
        return

    pending = await repo.count_pending_submissions(session, user.id)
    if pending >= settings.max_pending_per_user:
        await message.reply(
            f"У тебя уже {pending} кружков на модерации. Дождись решения по ним 🙏"
        )
        return

    submission = await repo.create_submission(
        session,
        from_user_id=user.id,
        from_username=user.username,
        from_first_name=user.first_name,
        file_id=video_note.file_id,
        file_unique_id=video_note.file_unique_id,
    )

    username = f" (@{user.username})" if user.username else ""
    try:
        info = await bot.send_message(
            settings.mod_chat_id,
            f"🎥 Заявка #{submission.id}\n"
            f"От: {user.full_name}{username}\n"
            f"user_id: <code>{user.id}</code>",
        )
        note = await bot.send_video_note(
            settings.mod_chat_id,
            video_note.file_id,
            reply_parameters=ReplyParameters(message_id=info.message_id),
            reply_markup=moderation_kb(submission.id),
        )
    except TelegramAPIError:
        log.exception(
            "failed to post submission %s to mod chat %s", submission.id, settings.mod_chat_id
        )
        await message.reply("Не получилось отправить на модерацию, попробуй позже 🙈")
        return  # session is not committed -> the submission row is rolled back

    submission.mod_chat_id = settings.mod_chat_id
    submission.mod_message_id = note.message_id
    await session.commit()
    log.info("submission=%s from user=%s posted for review", submission.id, user.id)

    await message.reply("🎬 Отправил на модерацию, спасибо! Сообщу, когда решат.")


@router.message(F.chat.type == "private", F.video)
async def on_plain_video(message: Message) -> None:
    await message.reply(
        "Пришли именно <b>видео-кружок</b> (кругляш), а не обычное видео. "
        "В Telegram: зажми кнопку записи видео в чате и смахни вверх."
    )
