"""match social

Revision ID: 0013
Revises: 0007
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invites",
        sa.Column(
            "target_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "invites",
        sa.Column(
            "source_game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_invites_source_game_id_creator_id",
        "invites",
        ["source_game_id", "creator_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_invites_source_game_id_creator_id", table_name="invites")
    op.drop_column("invites", "source_game_id")
    op.drop_column("invites", "target_user_id")
