from __future__ import annotations

from aiogram import Router

from . import (
    circles,
    common,
    idlists,
    moderation,
    profanity_watch,
    status,
    submissions,
)


def build_router() -> Router:
    router = Router()
    # order matters: specific private-chat handlers first, broad group watcher last
    router.include_router(common.router)
    router.include_router(status.router)
    router.include_router(idlists.router)
    router.include_router(circles.router)
    router.include_router(submissions.router)
    router.include_router(moderation.router)
    router.include_router(profanity_watch.router)
    return router
