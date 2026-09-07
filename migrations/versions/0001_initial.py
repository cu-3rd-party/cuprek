"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("from_user_id", sa.BigInteger(), nullable=False),
        sa.Column("from_username", sa.Text(), nullable=True),
        sa.Column("from_first_name", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("file_unique_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("mod_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("mod_message_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
    )
    op.create_index("ix_submissions_from_user_id", "submissions", ["from_user_id"])
    op.create_index("ix_submissions_from_user_status", "submissions", ["from_user_id", "status"])
    op.create_index("ix_submissions_file_unique_id", "submissions", ["file_unique_id"])

    op.create_table(
        "circles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("file_unique_id", sa.Text(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "submission_id",
            sa.BigInteger(),
            sa.ForeignKey("submissions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
        sa.UniqueConstraint("file_unique_id", name="uq_circles_file_unique_id"),
    )
    op.create_index("ix_circles_is_active", "circles", ["is_active"])

    op.create_table(
        "daily_activity",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("activity_date", sa.Date(), primary_key=True),
        sa.Column("profane_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circle_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("circle_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_activity")
    op.drop_index("ix_circles_is_active", table_name="circles")
    op.drop_table("circles")
    op.drop_index("ix_submissions_file_unique_id", table_name="submissions")
    op.drop_index("ix_submissions_from_user_status", table_name="submissions")
    op.drop_index("ix_submissions_from_user_id", table_name="submissions")
    op.drop_table("submissions")
