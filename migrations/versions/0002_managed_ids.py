"""managed_ids: runtime-editable admin / guaranteed lists

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_now = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "managed_ids",
        # "admin" | "guaranteed"
        sa.Column("kind", sa.Text(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=_now, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("managed_ids")
