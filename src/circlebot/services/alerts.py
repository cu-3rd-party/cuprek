"""Mirror WARNING+ log records into a Telegram chat.

The point is to learn that the bot broke without SSH-ing into the VPS: the detail
stays in `docker compose logs`, but the fact that something went wrong reaches the
mod chat. Three properties matter here and are easy to get wrong:

* ``emit`` never touches the network -- it only enqueues, so logging from the event
  loop stays non-blocking and a slow Telegram API cannot stall the bot.
* An alert that fails to send must not produce another alert. A context variable
  marks the window in which the handler is talking to Telegram, and records raised
  inside it are dropped.
* A crash loop must not turn into a message flood, so sends are rate-limited per
  window and identical texts are de-duplicated, with a "+N more suppressed" tail.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import sys
import time
from collections import deque

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..logging import build_formatter

# True while this handler is inside a Telegram call. aiogram logs its own retries and
# failures from that same task, so those records land in this context and get dropped.
_sending: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "circlebot_alert_sending", default=False
)

QUEUE_SIZE = 100
# Telegram caps messages at 4096 characters; leave room for the prefix and tail.
MAX_BODY_LEN = 3500
_LAST_SEEN_CAP = 256


class TelegramLogHandler(logging.Handler):
    """A ``logging.Handler`` that posts records to a chat from a background task.

    Not thread-safe by design: the bot is single-threaded asyncio, so ``emit`` and the
    drain task always run on the same loop.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        *,
        level: int = logging.WARNING,
        max_per_window: int = 8,
        window: float = 60.0,
        dedup_cooldown: float = 300.0,
    ) -> None:
        super().__init__(level=level)
        self._bot = bot
        self._chat_id = chat_id
        self._max_per_window = max_per_window
        self._window = window
        self._dedup_cooldown = dedup_cooldown

        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._sent_at: deque[float] = deque()
        self._last_seen: dict[str, float] = {}
        self._suppressed = 0
        self._task: asyncio.Task[None] | None = None

    # --- logging.Handler side: synchronous, must stay cheap ---

    def emit(self, record: logging.LogRecord) -> None:
        if _sending.get():
            return
        if record.name.startswith(__name__):
            return
        try:
            text = self.format(record)
        except Exception:  # formatting must never break the calling code
            self.handleError(record)
            return
        try:
            self._queue.put_nowait(text)
        except asyncio.QueueFull:
            self._suppressed += 1

    # --- background delivery ---

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="alerts-drain")

    async def aclose(self, timeout: float = 5.0) -> None:
        """Drain what is queued, then stop. Called on shutdown so the last error lands."""
        if self._task is None:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._queue.join(), timeout)
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self._deliver(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # a broken alerter must not kill the bot
                self._report(f"delivery failed: {exc!r}")
            finally:
                self._queue.task_done()

    def _allow(self, text: str, now: float) -> bool:
        last = self._last_seen.get(text)
        if last is not None and now - last < self._dedup_cooldown:
            return False
        while self._sent_at and now - self._sent_at[0] > self._window:
            self._sent_at.popleft()
        return len(self._sent_at) < self._max_per_window

    async def _deliver(self, text: str) -> None:
        now = time.monotonic()
        if not self._allow(text, now):
            self._suppressed += 1
            return

        self._sent_at.append(now)
        self._last_seen[text] = now
        if len(self._last_seen) > _LAST_SEEN_CAP:
            cutoff = now - self._dedup_cooldown
            self._last_seen = {k: v for k, v in self._last_seen.items() if v > cutoff}

        suppressed, self._suppressed = self._suppressed, 0
        body = text[:MAX_BODY_LEN]
        if suppressed:
            body = f"{body}\n\n(+{suppressed} more suppressed)"
        await self._send(f"\u26a0\ufe0f {body}")

    async def _send(self, text: str) -> None:
        token = _sending.set(True)
        try:
            # parse_mode=None: log lines contain arbitrary text and would break the
            # bot's default HTML parse mode.
            await self._bot.send_message(self._chat_id, text, parse_mode=None)
        except (TelegramAPIError, OSError) as exc:
            self._report(f"could not deliver alert: {exc!r}")
        finally:
            _sending.reset(token)

    @staticmethod
    def _report(message: str) -> None:
        # Deliberately not the logging module: that is what would close the loop.
        print(f"[alerts] {message}", file=sys.stderr, flush=True)


async def attach_telegram_alerts(
    bot: Bot,
    chat_id: int,
    *,
    level: str = "WARNING",
) -> TelegramLogHandler:
    """Install the handler on the root logger and start draining. Call inside the loop."""
    handler = TelegramLogHandler(
        bot,
        chat_id,
        level=getattr(logging, level.upper(), logging.WARNING),
    )
    handler.setFormatter(build_formatter())
    await handler.start()
    logging.getLogger().addHandler(handler)
    return handler


async def detach_telegram_alerts(handler: TelegramLogHandler | None) -> None:
    if handler is None:
        return
    logging.getLogger().removeHandler(handler)
    await handler.aclose()
