"""Runtime-editable privileged ID lists, with the database as the source of truth.

Two lists live here, both of which used to be ``.env``-only:

* ``admin``      -- who may use the admin commands and moderation buttons;
* ``guaranteed`` -- users who get a circle for *every* profane message
  (see ``handlers.profanity_watch``; the semantics are unchanged by this module,
  only where the IDs come from).

The values in ``.env`` become immutable **roots**. Commands can add and remove
database-backed IDs but never a root, so it is impossible to remove the last admin
and lock everyone out -- recovering from that would otherwise mean ``psql`` on the
server.

Reads are served from an in-process cache rather than the database, because
``profanity_watch.watch()`` consults ``is_guaranteed`` on *every* group message and
a round-trip per message is the wrong shape. That is safe because the bot is
single-instance by design (the same assumption ``KeyedLock`` already makes); a
second instance would need this replaced with a short-TTL cache or a LISTEN/NOTIFY
invalidation.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repo

log = logging.getLogger(__name__)

ADMIN = "admin"
GUARANTEED = "guaranteed"
KINDS = (ADMIN, GUARANTEED)


class IdRegistry:
    def __init__(
        self,
        root_admins: frozenset[int] = frozenset(),
        root_guaranteed: frozenset[int] = frozenset(),
    ) -> None:
        self._roots: dict[str, frozenset[int]] = {
            ADMIN: frozenset(root_admins),
            GUARANTEED: frozenset(root_guaranteed),
        }
        self._db: dict[str, set[int]] = {kind: set() for kind in KINDS}

    # -- reads -------------------------------------------------------------

    def roots(self, kind: str) -> frozenset[int]:
        return self._roots[kind]

    def managed(self, kind: str) -> set[int]:
        """Only the database-backed entries, i.e. the removable ones."""
        return set(self._db[kind])

    def effective(self, kind: str) -> set[int]:
        return set(self._roots[kind]) | self._db[kind]

    def is_root(self, kind: str, telegram_id: int) -> bool:
        return telegram_id in self._roots[kind]

    def contains(self, kind: str, telegram_id: int) -> bool:
        return telegram_id in self._roots[kind] or telegram_id in self._db[kind]

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and self.contains(ADMIN, telegram_id)

    def is_guaranteed(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and self.contains(GUARANTEED, telegram_id)

    # -- writes ------------------------------------------------------------

    async def load(self, session: AsyncSession) -> None:
        """Warm the cache from the database. Called once at startup."""
        stored = await repo.load_managed_ids(session)
        self._db = {kind: set(stored.get(kind, ())) for kind in KINDS}
        log.info(
            "id registry loaded: admins=%s (+%s root) guaranteed=%s (+%s root)",
            len(self._db[ADMIN]),
            len(self._roots[ADMIN]),
            len(self._db[GUARANTEED]),
            len(self._roots[GUARANTEED]),
        )

    async def add(
        self, session: AsyncSession, kind: str, telegram_id: int, added_by: int | None
    ) -> bool:
        """Store one ID. ``False`` means it was already in effect (root or stored).

        The caller commits; the cache is only updated once the row is flushed, so a
        failed transaction cannot leave the cache claiming an ID that is not stored.
        """
        if self.contains(kind, telegram_id):
            return False
        added = await repo.add_managed_id(session, kind, telegram_id, added_by)
        if added:
            self._db[kind].add(telegram_id)
        return added

    async def remove(self, session: AsyncSession, kind: str, telegram_id: int) -> bool:
        """Drop one ID. ``False`` means it was a root or was not stored at all."""
        if self.is_root(kind, telegram_id):
            return False
        removed = await repo.remove_managed_id(session, kind, telegram_id)
        self._db[kind].discard(telegram_id)
        return removed
