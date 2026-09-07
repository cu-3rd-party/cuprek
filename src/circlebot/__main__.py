from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError

from .config import get_settings
from .db.base import create_engine, create_sessionmaker
from .handlers import build_router
from .logging import setup_logging
from .middlewares.db_session import DbSessionMiddleware
from .services.locks import KeyedLock
from .services.profanity import ProfanityDetector

log = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    detector = ProfanityDetector.load(settings.data_path)
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(
        settings=settings,
        detector=detector,
        locks=KeyedLock(),
    )
    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(build_router())

    log.info(
        "starting bot: admins=%s mod_chat=%s watched_chats=%s tz=%s",
        sorted(settings.admin_ids),
        settings.mod_chat_id,
        sorted(settings.allowed_chat_ids) or "all",
        settings.timezone,
    )
    try:
        await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except TelegramUnauthorizedError:
        raise SystemExit("BOT_TOKEN is invalid — Telegram rejected it as Unauthorized") from None
    finally:
        await bot.session.close()
        await engine.dispose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
