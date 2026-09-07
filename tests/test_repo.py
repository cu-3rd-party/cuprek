"""Integration tests for the repository layer.

These tests DROP and recreate every table, so they run only against a dedicated
database whose name contains ``test``. Resolution order:

* ``TEST_DATABASE_URL`` if set;
* otherwise derived from ``DATABASE_URL`` by appending ``_test`` to the db name;
* otherwise the module is skipped.

The database is created automatically if it does not exist. Typical local run::

    docker compose up -d postgres
    export DATABASE_URL=postgresql+asyncpg://bot:bot@localhost:5432/circlebot
    pytest                       # uses circlebot_test
"""
from __future__ import annotations

import os
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from circlebot.db import repo
from circlebot.db.base import Base, create_sessionmaker


def _resolve_test_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    base = os.environ.get("DATABASE_URL")
    if not base:
        return None
    parts = urlsplit(base)
    db = parts.path.lstrip("/") or "circlebot"
    return urlunsplit(parts._replace(path=f"/{db}_test"))


TEST_DB_URL = _resolve_test_url()

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="set TEST_DATABASE_URL or DATABASE_URL to run repo tests"
)

if TEST_DB_URL and "test" not in urlsplit(TEST_DB_URL).path.lower():
    raise RuntimeError(
        f"refusing to run destructive repo tests against database "
        f"{urlsplit(TEST_DB_URL).path.lstrip('/')!r} — its name must contain 'test'"
    )


async def _ensure_database(url: str) -> None:
    parts = urlsplit(url)
    db_name = parts.path.lstrip("/")
    admin = create_async_engine(
        urlunsplit(parts._replace(path="/postgres")), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await admin.dispose()


@pytest_asyncio.fixture
async def sessionmaker():
    try:
        await _ensure_database(TEST_DB_URL)
        engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot reach test database: {exc}")
    yield create_sessionmaker(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_increment_creates_then_bumps(sessionmaker):
    day = date(2026, 9, 7)
    async with sessionmaker() as session:
        row = await repo.increment_profane_count(session, chat_id=1, user_id=2, day=day)
        assert row.profane_count == 1
        row = await repo.increment_profane_count(session, chat_id=1, user_id=2, day=day)
        assert row.profane_count == 2
        await session.commit()

    async with sessionmaker() as session:
        row = await repo.get_daily_activity(session, 1, 2, day)
        assert row is not None and row.profane_count == 2


async def test_mark_circle_sent_is_single_shot(sessionmaker):
    day = date(2026, 9, 7)
    async with sessionmaker() as session:
        await repo.add_circle(
            session,
            file_id="f",
            file_unique_id="u",
            duration=5,
            added_by=None,
            source="admin_dm",
        )
        await repo.increment_profane_count(session, chat_id=1, user_id=2, day=day)
        await session.commit()

    async with sessionmaker() as session:
        assert await repo.mark_circle_sent(session, 1, 2, day, circle_id=1) is True
        await session.commit()
    async with sessionmaker() as session:
        assert await repo.mark_circle_sent(session, 1, 2, day, circle_id=1) is False


async def test_circle_and_submission_dedup(sessionmaker):
    async with sessionmaker() as session:
        assert await repo.circle_exists(session, "abc") is False
        sub = await repo.create_submission(
            session,
            from_user_id=10,
            from_username="u",
            from_first_name="U",
            file_id="fid",
            file_unique_id="abc",
        )
        await session.commit()
        assert await repo.pending_submission_exists(session, "abc") is True
        assert await repo.count_pending_submissions(session, 10) == 1

        await repo.add_circle(
            session,
            file_id="fid",
            file_unique_id="abc",
            duration=None,
            added_by=10,
            source="submission",
            submission_id=sub.id,
        )
        await session.commit()
        assert await repo.circle_exists(session, "abc") is True


async def test_circle_soft_delete_and_restore(sessionmaker):
    async with sessionmaker() as session:
        circle = await repo.add_circle(
            session, file_id="f", file_unique_id="u", duration=1, added_by=None, source="admin_dm"
        )
        await session.commit()
        circle_id = circle.id

    async with sessionmaker() as session:
        assert await repo.pick_random_active_circle(session) is not None
        (await repo.get_circle(session, circle_id)).is_active = False
        await session.commit()

    async with sessionmaker() as session:
        assert await repo.pick_random_active_circle(session) is None
        assert await repo.count_circles(session, active_only=True) == 0
        assert await repo.count_circles(session, active_only=False) == 1
        (await repo.get_circle(session, circle_id)).is_active = True
        await session.commit()

    async with sessionmaker() as session:
        assert await repo.pick_random_active_circle(session) is not None


async def test_list_circles_order_and_filter(sessionmaker):
    async with sessionmaker() as session:
        for i in range(3):
            await repo.add_circle(
                session,
                file_id=f"f{i}",
                file_unique_id=f"u{i}",
                duration=None,
                added_by=None,
                source="admin_dm",
            )
        await session.commit()
        (await repo.get_circle(session, 1)).is_active = False
        await session.commit()

    async with sessionmaker() as session:
        active = await repo.list_circles(session, active_only=True)
        assert [c.id for c in active] == [3, 2]
        every = await repo.list_circles(session, active_only=False)
        assert [c.id for c in every] == [3, 2, 1]
        oldest_first = await repo.list_circles(session, active_only=False, newest_first=False)
        assert [c.id for c in oldest_first] == [1, 2, 3]


async def test_get_circle_by_submission(sessionmaker):
    async with sessionmaker() as session:
        sub = await repo.create_submission(
            session,
            from_user_id=1,
            from_username=None,
            from_first_name=None,
            file_id="f",
            file_unique_id="u",
        )
        await session.commit()
        await repo.add_circle(
            session,
            file_id="f",
            file_unique_id="u",
            duration=None,
            added_by=1,
            source="submission",
            submission_id=sub.id,
        )
        await session.commit()
        sub_id = sub.id

    async with sessionmaker() as session:
        found = await repo.get_circle_by_submission(session, sub_id)
        assert found is not None and found.submission_id == sub_id
        assert await repo.get_circle_by_submission(session, 999_999) is None
