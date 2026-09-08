from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..services.access import IdRegistry

router = Router(name="common")


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n\n"
        "Пришли мне <b>кружок</b>, где ты упрекаешь матершинников в чате "
        "(понятно, без матов). Если модераторы одобрят его добавление, "
        "кружок будет иногда прилетать тем, кто матерится в чатах. "
        "Мы поощряем креативность!"
    )


@router.message(Command("id"))
async def cmd_id(message: Message, registry: IdRegistry) -> None:
    is_private = message.chat.type == "private"
    user = message.from_user
    is_admin = user is not None and registry.is_admin(user.id)
    if not is_private and not is_admin:
        return
    lines = [
        f"chat_id: <code>{message.chat.id}</code>",
        f"chat_type: {message.chat.type}",
    ]
    if user is not None:
        lines.append(f"your user_id: <code>{user.id}</code>")
    await message.reply("\n".join(lines))
