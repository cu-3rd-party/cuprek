"""``/admins`` and ``/guaranteed`` -- edit the privileged ID lists without a redeploy.

Both commands take the same three shapes::

    /admins                 list
    /admins add 111 222     add one or more
    /admins rm 111          remove one or more

IDs from ``.env`` show up as roots and cannot be removed here (see
``services.access``); everything else is stored in the database and survives a
restart, which is the entire point of these commands.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import parse_int_set
from ..services.access import ADMIN, GUARANTEED, IdRegistry

router = Router(name="idlists")
log = logging.getLogger(__name__)

_TITLES = {
    ADMIN: ("админов", "Админы"),
    GUARANTEED: ("гарантированных", "Гарантированные кружки"),
}

_USAGE = (
    "Использование:\n"
    "<code>/{cmd}</code> — список\n"
    "<code>/{cmd} add 123456789</code> — добавить\n"
    "<code>/{cmd} rm 123456789</code> — убрать\n"
    "Можно несколько id через пробел или запятую."
)


def _render(registry: IdRegistry, kind: str, cmd: str) -> str:
    _, title = _TITLES[kind]
    roots = sorted(registry.roots(kind))
    managed = sorted(registry.managed(kind))

    lines = [f"<b>{title}</b>"]
    if not roots and not managed:
        lines.append("Список пуст.")
    if roots:
        lines.append("\nИз <code>.env</code> (убрать можно только там):")
        lines += [f"• <code>{i}</code> 🔒" for i in roots]
    if managed:
        lines.append("\nДобавленные командой:")
        lines += [f"• <code>{i}</code>" for i in managed]
    lines.append(f"\n<code>/{cmd} add|rm &lt;id&gt;</code>")
    return "\n".join(lines)


async def _handle(
    message: Message,
    session: AsyncSession,
    registry: IdRegistry,
    command: CommandObject,
    kind: str,
    cmd: str,
) -> None:
    user = message.from_user
    if not registry.is_admin(None if user is None else user.id):
        return

    args = (command.args or "").strip()
    if not args:
        await message.answer(_render(registry, kind, cmd))
        return

    verb, _, rest = args.partition(" ")
    verb = verb.lower()
    if verb not in {"add", "rm", "remove", "del"}:
        await message.reply(_USAGE.format(cmd=cmd))
        return

    try:
        ids = parse_int_set(rest)
    except (TypeError, ValueError):
        ids = set()
    if not ids:
        await message.reply(_USAGE.format(cmd=cmd))
        return

    genitive, _ = _TITLES[kind]
    done: list[int] = []
    skipped: list[str] = []

    if verb == "add":
        for telegram_id in sorted(ids):
            if await registry.add(session, kind, telegram_id, user.id if user else None):
                done.append(telegram_id)
            else:
                skipped.append(f"<code>{telegram_id}</code> — уже в списке")
        verb_done = "Добавил"
    else:
        for telegram_id in sorted(ids):
            if registry.is_root(kind, telegram_id):
                skipped.append(f"<code>{telegram_id}</code> — из <code>.env</code>, только там 🔒")
            elif await registry.remove(session, kind, telegram_id):
                done.append(telegram_id)
            else:
                skipped.append(f"<code>{telegram_id}</code> — и не было в списке")
        verb_done = "Убрал"

    await session.commit()

    parts: list[str] = []
    if done:
        parts.append(f"✅ {verb_done} {genitive}: " + ", ".join(f"<code>{i}</code>" for i in done))
        log.info(
            "%s %s %s by admin=%s", verb, kind, done, user.id if user else None
        )
    if skipped:
        parts.append("⚠️ Пропустил:\n" + "\n".join(f"• {s}" for s in skipped))
    parts.append(f"\nВсего сейчас: {len(registry.effective(kind))}")
    await message.reply("\n\n".join(parts))


@router.message(Command("admins"), F.chat.type == "private")
async def cmd_admins(
    message: Message,
    session: AsyncSession,
    registry: IdRegistry,
    command: CommandObject,
) -> None:
    await _handle(message, session, registry, command, ADMIN, "admins")


@router.message(Command("guaranteed"), F.chat.type == "private")
async def cmd_guaranteed(
    message: Message,
    session: AsyncSession,
    registry: IdRegistry,
    command: CommandObject,
) -> None:
    await _handle(message, session, registry, command, GUARANTEED, "guaranteed")
