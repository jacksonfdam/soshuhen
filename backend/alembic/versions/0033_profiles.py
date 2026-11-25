"""profiles: per-person data over one shared library

Revision ID: 0033_profiles
Revises: 0032_job_rerun_requested
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_profiles"
down_revision: str | None = "0032_job_rerun_requested"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each per-person table, its old key, and its new key. The key is where two
# people holding the same thing would otherwise collide.
KEYED = (
    ("provider_token", "provider_token_pkey", "p", ("provider",)),
    ("reading_position", "reading_position_pkey", "p", ("series_id",)),
    ("series_reader_pref", "series_reader_pref_pkey", "p", ("series_id",)),
    ("removed_entry", "removed_entry_pkey", "p", ("provider", "provider_media_id")),
    ("list_entry", "uq_list_entry_provider_media", "u", ("provider", "provider_media_id")),
)
UNKEYED = ("progress_event",)
NEW_UNIQUE = "uq_list_entry_profile_provider_media"


def upgrade() -> None:
    op.create_table(
        "profile",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("avatar", sa.String(20), nullable=False),
        sa.Column("pin_hash", sa.Text(), nullable=True),
        sa.Column("is_manager", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_profile_manager",
        "profile",
        ["is_manager"],
        unique=True,
        postgresql_where=sa.text("is_manager"),
    )
    op.execute("insert into profile (name, avatar, is_manager) values ('Me', 'avatar-01', true)")
    # A column default cannot hold a subquery; a function can.
    op.execute(
        """
        create function manager_profile_id() returns bigint
        language sql stable as $$ select id from profile where is_manager $$
        """
    )

    for table, constraint, kind, columns in KEYED:
        _add_profile_column_by_update(table)
        op.drop_constraint(constraint, table, type_="primary" if kind == "p" else "unique")
        if kind == "p":
            op.create_primary_key(constraint, table, ["profile_id", *columns])
        else:
            op.create_unique_constraint(NEW_UNIQUE, table, ["profile_id", *columns])
    for table in UNKEYED:
        _add_profile_column_by_update(table)

    op.create_table(
        "chapter_bookmark",
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            primary_key=True,
            server_default=sa.text("manager_profile_id()"),
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger(),
            sa.ForeignKey("chapter.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.execute(
        """
        insert into chapter_bookmark (profile_id, chapter_id)
        select (select id from profile where is_manager), id from chapter where bookmarked
        """
    )
    op.drop_column("chapter", "bookmarked")

    op.create_table(
        "notification_read",
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            primary_key=True,
            server_default=sa.text("manager_profile_id()"),
        ),
        sa.Column(
            "notification_id",
            sa.BigInteger(),
            sa.ForeignKey("notification.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        """
        insert into notification_read (profile_id, notification_id, read_at)
        select (select id from profile where is_manager), id, read_at
          from notification where read_at is not null
        """
    )
    op.drop_index("ix_notification_unread", table_name="notification")
    op.drop_column("notification", "read_at")


def _add_profile_column_by_update(table: str) -> None:
    # The default is the managing profile, the same rule the API applies to a
    # request that names none. Every writer that acts for someone else must
    # say so; the per-profile tests are what catch one that forgets.
    op.add_column(
        table,
        sa.Column(
            "profile_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("manager_profile_id()"),
        ),
    )
    op.create_foreign_key(
        f"fk_{table}_profile", table, "profile", ["profile_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    manager = "(select id from profile where is_manager)"

    op.add_column("notification", sa.Column("read_at", sa.DateTime(timezone=True)))
    op.execute(
        f"""
        update notification n set read_at = r.read_at
          from notification_read r
         where r.notification_id = n.id and r.profile_id = {manager}
        """
    )
    op.create_index(
        "ix_notification_unread",
        "notification",
        ["created_at"],
        postgresql_where=sa.text("read_at is null"),
    )
    op.drop_table("notification_read")

    op.add_column(
        "chapter",
        sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        f"""
        update chapter set bookmarked = true
         where id in (select chapter_id from chapter_bookmark where profile_id = {manager})
        """
    )
    op.drop_table("chapter_bookmark")

    # Only the manager's rows fit the old one-person keys; everyone else's go.
    for table in (*(k[0] for k in KEYED), *UNKEYED):
        op.execute(f"delete from {table} where profile_id <> {manager}")

    for table, constraint, kind, columns in KEYED:
        if kind == "p":
            op.drop_constraint(constraint, table, type_="primary")
            op.create_primary_key(constraint, table, list(columns))
        else:
            op.drop_constraint(NEW_UNIQUE, table, type_="unique")
            op.create_unique_constraint(constraint, table, list(columns))
    for table in (*(k[0] for k in KEYED), *UNKEYED):
        op.drop_constraint(f"fk_{table}_profile", table, type_="foreignkey")
        op.drop_column(table, "profile_id")

    op.execute("drop function manager_profile_id()")
    op.drop_index("uq_profile_manager", table_name="profile")
    op.drop_table("profile")
