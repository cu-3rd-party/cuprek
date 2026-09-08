from __future__ import annotations

import logging
import sys
import time

# Timestamps are always UTC and say so. A VPS normally runs UTC while the bot's
# business day follows TIMEZONE, and an unlabelled local timestamp is genuinely
# ambiguous when you are reading `docker compose logs` from somewhere else.
LOG_FORMAT = "%(asctime)sZ %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_formatter() -> logging.Formatter:
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    formatter.converter = time.gmtime
    return formatter


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(build_formatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)

    # aiogram is chatty at INFO for every update; keep it at WARNING.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
