from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Submission(Base):
    """A circle sent to the bot in DM, awaiting / holding a moderation decision."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    from_username: Mapped[str | None] = mapped_column(Text)
    from_first_name: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str] = mapped_column(Text)
    file_unique_id: Mapped[str] = mapped_column(Text, index=True)
    # pending | accepted | rejected | duplicate
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    mod_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Circle(Base):
    """An approved video note that can be sent to a cursing user."""

    __tablename__ = "circles"
    __table_args__ = (UniqueConstraint("file_unique_id", name="uq_circles_file_unique_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    file_id: Mapped[str] = mapped_column(Text)
    file_unique_id: Mapped[str] = mapped_column(Text)
    duration: Mapped[int | None] = mapped_column(Integer)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text)  # admin_dm | submission
    submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DailyActivity(Base):
    """Per (chat, user, local date) profanity counter and one-circle-per-day flag."""

    __tablename__ = "daily_activity"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    activity_date: Mapped[date] = mapped_column(Date, primary_key=True)
    profane_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    circle_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    circle_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ManagedId(Base):
    """A Telegram ID added to a privileged list at runtime, via an admin command.

    Complements the ``ADMIN_IDS`` / ``GUARANTEED_CIRCLE_IDS`` values in ``.env``:
    those stay as immutable "root" entries so the bot can never be left without an
    admin, while everything here can be added and removed without a redeploy.
    """

    __tablename__ = "managed_ids"

    # "admin" | "guaranteed" -- one table with a discriminator keeps the repo
    # helpers to a single set of functions instead of two parallel ones.
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
