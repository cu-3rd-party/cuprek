"""``/status`` -- a deploy sanity check that fits on a phone screen.

Answers the questions you would otherwise SSH in for: is this the bot I think it is,
on the build I think it is, can it reach the database, and is the heartbeat alive.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db import repo
from ..health import age_seconds

router = Router(name="status")
log = logging.getLogger(__name__)


def format_uptime(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds_left = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds_left}s"


@router.message(Command("status"), F.chat.type == "private")
async def cmd_status(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    started_at: datetime,
) -> None:
    user = message.from_user
    if user is None or user.id not in settings.admin_ids:
        return

    me = await bot.me()  # cached by aiogram after the first call
    uptime = format_uptime((datetime.now(UTC) - started_at).total_seconds())

    lines = [
        f"🤖 @{me.username} <code>{me.id}</code>",
        f"build: <code>{settings.git_sha}</code>",
        f"uptime: {uptime} (since {started_at:%Y-%m-%d %H:%M}Z)",
    ]

    try:
        t0 = time.perf_counter()
        await session.execute(text("SELECT 1"))
        db_ms = (time.perf_counter() - t0) * 1000
        active = await repo.count_circles(session, active_only=True)
        total = await repo.count_circles(session, active_only=False)
        pending = await repo.count_pending_submissions(session)
    except SQLAlchemyError as exc:
        log.warning("/status: database check failed: %s", exc)
        lines.append(f"db: ❌ {type(exc).__name__}")
    else:
        lines.append(f"db: ✅ {db_ms:.0f} ms")
        lines.append(f"circles: {active} active / {total} total")
        lines.append(f"pending submissions: {pending}")

    age = age_seconds(Path(settings.heartbeat_file))
    if age is None:
        lines.append("heartbeat: ❌ missing")
    elif age > settings.heartbeat_max_age:
        lines.append(f"heartbeat: ⚠️ {age:.0f}s old")
    else:
        lines.append(f"heartbeat: ✅ {age:.0f}s ago")

    lines.append(f"tz: {settings.timezone} · log level: {settings.log_level}")
    await message.answer("\n".join(lines))
