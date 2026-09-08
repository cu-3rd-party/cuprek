from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.types import User
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .config import get_settings
from .db import repo
from .db.base import create_engine, create_sessionmaker
from .handlers import build_router
from .logging import setup_logging
from .middlewares.db_session import DbSessionMiddleware
from .services.access import ADMIN, GUARANTEED, IdRegistry
from .services.alerts import attach_telegram_alerts, detach_telegram_alerts
from .services.heartbeat import heartbeat_loop, ping_db
from .services.locks import KeyedLock
from .services.profanity import ProfanityDetector
from .services.runtime_config import resolve_profanity_config

log = logging.getLogger(__name__)


async def _identify(bot: Bot) -> User:
    """Resolve who we are. The first thing worth knowing from a remote log."""
    try:
        return await bot.me()
    except TelegramUnauthorizedError:
        log.critical("BOT_TOKEN is invalid \u2014 Telegram rejected it as Unauthorized")
        raise SystemExit(2) from None
    except TelegramAPIError as exc:
        log.critical("cannot reach Telegram at startup: %s", exc)
        raise SystemExit(3) from None


async def _check_database(
    engine: AsyncEngine, sessionmaker: async_sessionmaker[AsyncSession]
) -> int:
    """Prove the DB is usable before polling starts.

    Without this a bad DATABASE_URL only shows up as a traceback per update, which
    reads like a bot bug rather than a configuration mistake.
    """
    try:
        await ping_db(engine)
        async with sessionmaker() as session:
            return await repo.count_circles(session, active_only=True)
    except (SQLAlchemyError, OSError) as exc:
        log.critical("database unreachable at startup: %s", exc)
        raise SystemExit(4) from None


def _install_signal_handlers(stop: asyncio.Event) -> None:
    def _on_signal(sig: signal.Signals) -> None:
        log.info("received %s, shutting down", sig.name)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Windows dev boxes have no add_signal_handler; Ctrl+C still works.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _on_signal, sig)


async def _run_polling(dp: Dispatcher, bot: Bot) -> None:
    """Poll until Telegram stops us or a signal arrives.

    Racing polling against a signal event (rather than letting SIGTERM kill the
    process outright) is what makes `docker compose restart` log a clean shutdown
    instead of looking like a crash, and lets the engine and session close properly.
    """
    stop = asyncio.Event()
    _install_signal_handlers(stop)

    polling = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
        name="polling",
    )
    stopper = asyncio.create_task(stop.wait(), name="stop-signal")

    done, pending = await asyncio.wait({polling, stopper}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if polling in done:
        polling.result()  # re-raise whatever ended polling on its own


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    started_at = datetime.now(UTC)

    detector = ProfanityDetector.load(settings.data_path)
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # Roots come from .env and can never be removed by a command; everything else
    # is loaded from the database below and is editable at runtime.
    registry = IdRegistry(
        root_admins=frozenset(settings.admin_ids),
        root_guaranteed=frozenset(settings.guaranteed_circle_ids),
    )
    dp = Dispatcher(
        settings=settings,
        detector=detector,
        locks=KeyedLock(),
        registry=registry,
        started_at=started_at,
    )
    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(build_router())

    alerts = None
    heartbeat: asyncio.Task[None] | None = None
    try:
        me = await _identify(bot)
        circles = await _check_database(engine, sessionmaker)
        async with sessionmaker() as session:
            await registry.load(session)
        log.info(
            "starting bot=@%s id=%s build=%s circles=%s admins=%s mod_chat=%s "
            "watched_chats=%s guaranteed=%s tz=%s",
            me.username,
            me.id,
            settings.git_sha,
            circles,
            sorted(registry.effective(ADMIN)),
            settings.mod_chat_id,
            sorted(settings.allowed_chat_ids) or "all",
            sorted(registry.effective(GUARANTEED)) or "none",
            settings.timezone,
        )
        if circles == 0:
            log.warning("circle pool is empty \u2014 the bot has nothing to reply with yet")

        async with sessionmaker() as session:
            overrides = await repo.get_bot_settings(session)
        curve = resolve_profanity_config(overrides, settings)
        log.info(
            "profanity curve: free=%s base=%g%% step=%g%% overrides=%s",
            curve.free_messages,
            curve.base_chance,
            curve.step,
            ", ".join(sorted(overrides)) or "none",
        )

        if settings.alert_enabled:
            alerts = await attach_telegram_alerts(
                bot, settings.alert_target_chat_id, level=settings.alert_level
            )
            log.info(
                "log alerts -> chat=%s at %s",
                settings.alert_target_chat_id,
                settings.alert_level.upper(),
            )

        heartbeat = asyncio.create_task(
            heartbeat_loop(engine, Path(settings.heartbeat_file), settings.heartbeat_interval),
            name="heartbeat",
        )

        await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        log.info("polling started")
        await _run_polling(dp, bot)
        log.info("polling stopped")
    except TelegramUnauthorizedError:
        log.critical("BOT_TOKEN was rejected while running \u2014 was it revoked?")
        raise SystemExit(2) from None
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        # Flush pending alerts before the session that sends them is closed.
        await detach_telegram_alerts(alerts)
        await bot.session.close()
        await engine.dispose()
        log.info("shutdown complete")


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
