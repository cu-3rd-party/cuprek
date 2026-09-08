"""Database access helpers. Every function takes an ``AsyncSession`` and does not commit."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Circle, DailyActivity, Submission

# ---------------------------------------------------------------------------
# circles
# ---------------------------------------------------------------------------


async def pick_random_active_circle(session: AsyncSession) -> Circle | None:
    """Return a random active circle.

    ``ORDER BY random()`` is fine for a modest pool. If the table ever grows to
    hundreds of thousands of rows, switch to ``OFFSET floor(random() * count)``.
    """
    stmt = select(Circle).where(Circle.is_active.is_(True)).order_by(func.random()).limit(1)
    return await session.scalar(stmt)


async def count_circles(session: AsyncSession, *, active_only: bool = True) -> int:
    stmt = select(func.count()).select_from(Circle)
    if active_only:
        stmt = stmt.where(Circle.is_active.is_(True))
    return int(await session.scalar(stmt) or 0)


async def count_active_circles(session: AsyncSession) -> int:
    return await count_circles(session, active_only=True)


async def list_circles(
    session: AsyncSession,
    *,
    active_only: bool = True,
    limit: int = 20,
    newest_first: bool = True,
) -> list[Circle]:
    stmt = select(Circle)
    if active_only:
        stmt = stmt.where(Circle.is_active.is_(True))
    stmt = stmt.order_by(Circle.id.desc() if newest_first else Circle.id.asc()).limit(limit)
    return list(await session.scalars(stmt))


async def get_circle(session: AsyncSession, circle_id: int) -> Circle | None:
    return await session.get(Circle, circle_id)


async def get_circle_by_submission(
    session: AsyncSession, submission_id: int
) -> Circle | None:
    stmt = select(Circle).where(Circle.submission_id == submission_id).limit(1)
    return await session.scalar(stmt)


async def circle_exists(session: AsyncSession, file_unique_id: str) -> bool:
    stmt = select(Circle.id).where(Circle.file_unique_id == file_unique_id).limit(1)
    return await session.scalar(stmt) is not None


async def add_circle(
    session: AsyncSession,
    *,
    file_id: str,
    file_unique_id: str,
    duration: int | None,
    added_by: int | None,
    source: str,
    submission_id: int | None = None,
) -> Circle:
    circle = Circle(
        file_id=file_id,
        file_unique_id=file_unique_id,
        duration=duration,
        added_by=added_by,
        source=source,
        submission_id=submission_id,
        is_active=True,
    )
    session.add(circle)
    await session.flush()
    return circle


# ---------------------------------------------------------------------------
# submissions
# ---------------------------------------------------------------------------


async def pending_submission_exists(session: AsyncSession, file_unique_id: str) -> bool:
    stmt = (
        select(Submission.id)
        .where(Submission.file_unique_id == file_unique_id, Submission.status == "pending")
        .limit(1)
    )
    return await session.scalar(stmt) is not None


async def count_pending_submissions(session: AsyncSession, user_id: int | None = None) -> int:
    """Pending submissions for one user, or across everyone when ``user_id`` is None."""
    stmt = select(func.count()).select_from(Submission).where(Submission.status == "pending")
    if user_id is not None:
        stmt = stmt.where(Submission.from_user_id == user_id)
    return int(await session.scalar(stmt) or 0)


async def create_submission(
    session: AsyncSession,
    *,
    from_user_id: int,
    from_username: str | None,
    from_first_name: str | None,
    file_id: str,
    file_unique_id: str,
) -> Submission:
    sub = Submission(
        from_user_id=from_user_id,
        from_username=from_username,
        from_first_name=from_first_name,
        file_id=file_id,
        file_unique_id=file_unique_id,
        status="pending",
    )
    session.add(sub)
    await session.flush()
    return sub


async def get_submission_for_update(
    session: AsyncSession, submission_id: int
) -> Submission | None:
    """Load a submission with ``SELECT ... FOR UPDATE`` to serialise moderator clicks."""
    return await session.get(Submission, submission_id, with_for_update=True)


# ---------------------------------------------------------------------------
# daily activity
# ---------------------------------------------------------------------------


async def get_daily_activity(
    session: AsyncSession, chat_id: int, user_id: int, day: date
) -> DailyActivity | None:
    return await session.get(DailyActivity, (chat_id, user_id, day))


async def increment_profane_count(
    session: AsyncSession, chat_id: int, user_id: int, day: date
) -> DailyActivity:
    """Bump (or create) the per-day counter and return the fresh row.

    Callers hold a per-(chat, user) in-process lock, so the read-modify-write is
    safe for a single bot instance. For a multi-instance deployment replace this
    with ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING``.
    """
    row = await session.get(DailyActivity, (chat_id, user_id, day))
    if row is None:
        row = DailyActivity(
            chat_id=chat_id, user_id=user_id, activity_date=day, profane_count=1
        )
        session.add(row)
    else:
        row.profane_count += 1
    await session.flush()
    return row


async def mark_circle_sent(
    session: AsyncSession, chat_id: int, user_id: int, day: date, circle_id: int
) -> bool:
    """Atomically claim the day's single circle slot. Returns ``False`` if already claimed."""
    stmt = (
        update(DailyActivity)
        .where(
            DailyActivity.chat_id == chat_id,
            DailyActivity.user_id == user_id,
            DailyActivity.activity_date == day,
            DailyActivity.circle_sent.is_(False),
        )
        .values(circle_sent=True, circle_id=circle_id)
    )
    result = await session.execute(stmt)
    return (result.rowcount or 0) > 0
