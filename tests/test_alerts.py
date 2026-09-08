"""The alert handler's job is to be safe under failure, not to be clever.

These cover the three ways a log-to-Telegram bridge normally goes wrong: it floods
the chat during a crash loop, it blocks the event loop, or it alerts about its own
failure to alert and never stops.
"""
from __future__ import annotations

import logging

from circlebot.services.alerts import QUEUE_SIZE, TelegramLogHandler


class FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        if self.fail:
            raise OSError("network down")
        self.sent.append(text)


def make_handler(bot: object, **kwargs: object) -> TelegramLogHandler:
    handler = TelegramLogHandler(bot, 1, **kwargs)  # type: ignore[arg-type]
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    return handler


def make_record(msg: str, level: int = logging.WARNING) -> logging.LogRecord:
    return logging.LogRecord("test", level, __file__, 1, msg, None, None)


async def drain(handler: TelegramLogHandler, messages: list[str]) -> None:
    await handler.start()
    for message in messages:
        handler.emit(make_record(message))
    await handler.aclose()


async def test_delivers_a_warning() -> None:
    bot = FakeBot()
    await drain(make_handler(bot), ["disk on fire"])
    assert len(bot.sent) == 1
    assert "disk on fire" in bot.sent[0]


async def test_identical_messages_are_deduplicated_within_the_cooldown() -> None:
    bot = FakeBot()
    await drain(make_handler(bot, dedup_cooldown=300.0), ["same", "same", "same"])
    assert len(bot.sent) == 1


async def test_suppressed_count_rides_along_on_the_next_alert() -> None:
    bot = FakeBot()
    await drain(make_handler(bot, dedup_cooldown=300.0), ["same", "same", "different"])
    assert len(bot.sent) == 2
    assert "+1 more suppressed" in bot.sent[1]


async def test_rate_limit_caps_a_crash_loop() -> None:
    bot = FakeBot()
    handler = make_handler(bot, max_per_window=2, window=60.0, dedup_cooldown=0.0)
    await drain(handler, ["a", "b", "c", "d", "e"])
    assert len(bot.sent) == 2


async def test_emit_never_raises_when_the_queue_is_full() -> None:
    # No drain task started, so nothing is consumed.
    handler = make_handler(FakeBot())
    for i in range(QUEUE_SIZE + 5):
        handler.emit(make_record(f"msg {i}"))
    assert handler._suppressed == 5


async def test_a_failing_send_does_not_alert_about_itself() -> None:
    """The guard that stops an alert failure from generating more alerts."""
    accepted: list[int] = []

    class ReentrantBot(FakeBot):
        handler: TelegramLogHandler

        async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
            self.sent.append(text)
            before = self.handler._queue.qsize()
            # Exactly what aiogram does when a send fails: log from inside the call.
            self.handler.emit(make_record("could not send", logging.ERROR))
            accepted.append(self.handler._queue.qsize() - before)

    bot = ReentrantBot()
    handler = make_handler(bot)
    bot.handler = handler
    await drain(handler, ["first"])

    assert accepted == [0]
    assert len(bot.sent) == 1


async def test_a_dead_telegram_does_not_break_the_bot() -> None:
    bot = FakeBot(fail=True)
    await drain(make_handler(bot), ["still logging"])
    assert bot.sent == []
