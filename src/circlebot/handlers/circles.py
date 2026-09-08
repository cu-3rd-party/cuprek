from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repo
from ..keyboards import CircleAction, circle_row_kb, flip_circle_buttons
from ..services.access import IdRegistry

router = Router(name="circles")
log = logging.getLogger(__name__)

GALLERY_CAP = 20
SEND_GAP = 0.3  # seconds between video notes — stay under Telegram's per-chat rate limit


def _is_admin(message: Message, registry: IdRegistry) -> bool:
    return message.from_user is not None and registry.is_admin(message.from_user.id)


@router.message(Command("circles"), F.chat.type == "private")
async def cmd_circles(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    registry: IdRegistry,
    command: CommandObject,
) -> None:
    if not _is_admin(message, registry):
        return

    show_all = (command.args or "").strip().lower() == "all"
    n_active = await repo.count_circles(session, active_only=True)
    circles = await repo.list_circles(session, active_only=not show_all, limit=GALLERY_CAP)

    if not circles:
        await message.answer("В базе пока нет кружков." if not show_all else "Кружков нет вообще.")
        return

    head = f"Кружков активных: {n_active}"
    if show_all:
        n_all = await repo.count_circles(session, active_only=False)
        head += f" · неактивных: {n_all - n_active}"
    head += f"\nПоказываю до {GALLERY_CAP}, новые сверху."
    await message.answer(head)

    for circle in circles:
        with contextlib.suppress(TelegramAPIError):
            await bot.send_video_note(
                message.chat.id,
                circle.file_id,
                reply_markup=circle_row_kb(circle.id, active=circle.is_active),
            )
        await asyncio.sleep(SEND_GAP)

    if not show_all and n_active > GALLERY_CAP:
        await message.answer("…показаны не все. Удали часть и вызови /circles снова.")


@router.message(Command("rmcircle"), F.chat.type == "private")
async def cmd_rmcircle(
    message: Message,
    session: AsyncSession,
    registry: IdRegistry,
    command: CommandObject,
) -> None:
    if not _is_admin(message, registry):
        return

    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.reply("Использование: <code>/rmcircle 5</code> (id — из /circles)")
        return

    circle = await repo.get_circle(session, int(raw))
    if circle is None:
        await message.reply(f"Кружка #{raw} нет.")
        return
    if not circle.is_active:
        await message.reply(f"Кружок #{raw} уже удалён. Вернуть: <code>/circles all</code>")
        return

    circle.is_active = False
    await session.commit()
    await message.reply(f"🗑 Кружок #{raw} удалён. Вернуть: <code>/circles all</code>")


@router.callback_query(CircleAction.filter())
async def on_circle_action(
    callback: CallbackQuery,
    callback_data: CircleAction,
    session: AsyncSession,
    registry: IdRegistry,
) -> None:
    if not registry.is_admin(callback.from_user.id):
        await callback.answer("Только для админов 🙅", show_alert=True)
        return

    circle = await repo.get_circle(session, callback_data.circle_id)
    if circle is None:
        await callback.answer("Кружок не найден", show_alert=True)
        return

    want_active = callback_data.action == "restore"
    if circle.is_active != want_active:
        circle.is_active = want_active
        await session.commit()

    if callback.message is not None:
        with contextlib.suppress(TelegramAPIError):
            await callback.message.edit_reply_markup(
                reply_markup=flip_circle_buttons(
                    callback.message.reply_markup,
                    callback_data.circle_id,
                    now_active=want_active,
                )
            )
    await callback.answer("Вернул ♻️" if want_active else "Удалил 🗑")
