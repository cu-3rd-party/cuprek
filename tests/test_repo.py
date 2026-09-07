"""Integration tests for the repository layer.

Requires a reachable PostgreSQL. Set ``TEST_DATABASE_URL`` (SQLAlchemy async URL),
e.g. ``postgresql+asyncpg://bot:bot@localhost:5432/circlebot`` after
``docker compose up -d postgres``. The whole module is skipped when the database
is not available.
"""
from __future__ import annotations

import os
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from circlebot.db import repo
from circlebot.db.base import Base, create_sessionmaker

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL is not set")


@pytest_asyncio.fixture
async def sessionmaker():
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
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
