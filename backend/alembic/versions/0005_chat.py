"""chat: game_messages

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22

"""
import sqlalchemy as sa
from alembic import op
from collections.abc import Sequence

import sqlalchemy.dialects.postgresql as pg

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 300",
            name=op.f("ck_game_messages_body_length"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_game_messages_game_id_games")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_game_messages_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_messages")),
    )
    op.create_index("ix_game_messages_game_id_id", "game_messages", ["game_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_game_messages_game_id_id", table_name="game_messages")
    op.drop_table("game_messages")
