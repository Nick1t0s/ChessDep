"""social: friendships, notifications, invite_deliveries

Revision ID: 0011
Revises: 0005
Create Date: 2026-11-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
import sqlalchemy.dialects.postgresql as pg

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOTIFICATION_KINDS = (
    "friend_request, friend_accepted, match_invite, market_sale, gift"
).replace(", ", "', '")


def upgrade() -> None:
    # 1. friendships
    op.create_table(
        "friendships",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_low_id", sa.BigInteger(), nullable=False),
        sa.Column("user_high_id", sa.BigInteger(), nullable=False),
        sa.Column("requester_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            pg.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            pg.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "user_low_id < user_high_id",
            name=op.f("ck_friendships_user_order"),
        ),
        sa.CheckConstraint(
            "requester_id = user_low_id OR requester_id = user_high_id",
            name=op.f("ck_friendships_requester_in_pair"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted')",
            name=op.f("ck_friendships_status_whitelist"),
        ),
        sa.ForeignKeyConstraint(
            ["user_low_id"],
            ["users.id"],
            name=op.f("fk_friendships_user_low_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_high_id"],
            ["users.id"],
            name=op.f("fk_friendships_user_high_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_friendships_requester_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friendships")),
        sa.UniqueConstraint("user_low_id", "user_high_id", name="uq_friendships_canonical_pair"),
    )
    op.create_index("ix_friendships_user_low_status", "friendships", ["user_low_id", "status"])
    op.create_index("ix_friendships_user_high_status", "friendships", ["user_high_id", "status"])
    op.create_index("ix_friendships_requester_status", "friendships", ["requester_id", "status"])

    # 2. notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("href", sa.Text(), nullable=True),
        sa.Column("read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            pg.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"kind IN ('{_NOTIFICATION_KINDS}')",
            name=op.f("ck_notifications_kind_whitelist"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index("ix_notifications_user_id_id", "notifications", ["user_id", "id"])
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "read"])

    # 3. invite_deliveries
    op.create_table(
        "invite_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            pg.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["code"],
            ["invites.code"],
            name=op.f("fk_invite_deliveries_code_invites"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_invite_deliveries_recipient_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite_deliveries")),
        sa.UniqueConstraint(
            "code", "recipient_id", name="uq_invite_deliveries_code_recipient"
        ),
    )
    op.create_index(
        "ix_invite_deliveries_recipient_id", "invite_deliveries", ["recipient_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_invite_deliveries_recipient_id", table_name="invite_deliveries")
    op.drop_table("invite_deliveries")

    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_id_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_friendships_requester_status", table_name="friendships")
    op.drop_index("ix_friendships_user_high_status", table_name="friendships")
    op.drop_index("ix_friendships_user_low_status", table_name="friendships")
    op.drop_table("friendships")
