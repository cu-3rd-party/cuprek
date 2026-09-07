from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import repo
from ..keyboards import SubAction, decided_kb

router = Router(name="moderation")
log = logging.getLogger(__name__)

_TOAST = {
    "accepted": "Принято ✅",
    "rejected": "Отклонено ❌",
    "duplicate": "Такой кружок уже есть ♻️",
}
_CARD_LABEL = {
    "accepted": "✅ Принято",
    "rejected": "❌ Отклонено",
    "duplicate": "♻️ Дубликат",
}
_AUTHOR_NOTE = {
    "accepted": "✅ Твой кружок приняли! Теперь он может прилетать матерящимся в чатах.",
    "rejected": "❌ Твой кружок отклонили.",
    "duplicate": "♻️ Такой кружок уже есть в базе, но спасибо!",
}


@router.callback_query(SubAction.filter())
async def on_moderation(
    callback: CallbackQuery,
    callback_data: SubAction,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Решать могут только модераторы 🙅", show_alert=True)
        return

    if callback_data.action == "done":
        await callback.answer()
        return

    submission = await repo.get_submission_for_update(session, callback_data.sub_id)
    if submission is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if submission.status != "pending":
        await callback.answer(f"Уже обработано: {submission.status}")
        existing = (
            await repo.get_circle_by_submission(session, submission.id)
            if submission.status == "accepted"
            else None
        )
        await _refresh_card(
            callback,
            submission.status,
            submission.id,
            circle_id=existing.id if existing else None,
            circle_active=existing.is_active if existing else True,
        )
        return

    new_circle_id: int | None = None
    if callback_data.action == "accept":
        if await repo.circle_exists(session, submission.file_unique_id):
            submission.status = "duplicate"
        else:
            circle = await repo.add_circle(
                session,
                file_id=submission.file_id,
                file_unique_id=submission.file_unique_id,
                duration=None,
                added_by=submission.from_user_id,
                source="submission",
                submission_id=submission.id,
            )
            submission.status = "accepted"
            new_circle_id = circle.id
    else:
        submission.status = "rejected"

    submission.reviewed_by = callback.from_user.id
    submission.reviewed_at = datetime.now(UTC)
    await session.commit()

    await _refresh_card(
        callback,
        submission.status,
        submission.id,
        callback.from_user.full_name,
        circle_id=new_circle_id,
    )
    await callback.answer(_TOAST.get(submission.status, submission.status))
    await _notify_author(bot, submission.from_user_id, submission.status)


async def _refresh_card(
    callback: CallbackQuery,
    status: str,
    sub_id: int,
    moderator: str = "",
    *,
    circle_id: int | None = None,
    circle_active: bool = True,
) -> None:
    if callback.message is None:
        return
    label = _CARD_LABEL.get(status, status)
    if moderator:
        label = f"{label} · {moderator}"
    with contextlib.suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(
            reply_markup=decided_kb(
                label, sub_id=sub_id, circle_id=circle_id, circle_active=circle_active
            )
        )


async def _notify_author(bot: Bot, user_id: int, status: str) -> None:
    text = _AUTHOR_NOTE.get(status)
    if not text:
        return
    try:
        await bot.send_message(user_id, text)
    except TelegramAPIError:
        log.info("could not notify submission author %s (blocked bot?)", user_id)
