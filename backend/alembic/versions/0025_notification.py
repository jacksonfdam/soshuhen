"""notification: what a discovery run found new, per series

Revision ID: 0025_notification
Revises: 0024_list_entry_volumes
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_notification"
down_revision: str | None = "0024_list_entry_volumes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "series_id",
            sa.Integer(),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_number", sa.Numeric(8, 2), nullable=False),
        sa.Column("last_number", sa.Numeric(8, 2), nullable=False),
        sa.Column("volume_number", sa.Numeric(8, 2)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notification_created", "notification", [sa.text("created_at desc")])
    # The bell's badge counts only these, and they are the few rows among many.
    op.create_index(
        "ix_notification_unread",
        "notification",
        ["created_at"],
        postgresql_where=sa.text("read_at is null"),
    )


def downgrade() -> None:
    op.drop_table("notification")
