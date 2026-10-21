"""games, invites, active_players, game_events, rolls

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21

"""
import sqlalchemy as sa
from alembic import op
from collections.abc import Sequence
from sqlalchemy.dialects.postgresql import JSONB

import sqlalchemy.dialects.postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("time_control", sa.Text(), nullable=False),
        sa.Column("base_ms", sa.Integer(), nullable=False),
        sa.Column("inc_ms", sa.Integer(), nullable=False),
        sa.Column("white_id", sa.BigInteger(), nullable=False),
        sa.Column("black_id", sa.BigInteger(), nullable=False),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("ply", sa.Integer(), server_default="0", nullable=False),
        sa.Column("repetition", JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("white_ms", sa.BigInteger(), nullable=False),
        sa.Column("black_ms", sa.BigInteger(), nullable=False),
        sa.Column("turn_started_at", pg.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "clock_running", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("abort_deadline", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "dep_used_this_turn", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("white_deps", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("black_deps", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("draw_offer_by", sa.Text(), nullable=True),
        sa.Column("white_last_offer_ply", sa.Integer(), nullable=True),
        sa.Column("black_last_offer_ply", sa.Integer(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("white_loadout", JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("black_loadout", JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("white_elo_before", sa.Integer(), nullable=False),
        sa.Column("black_elo_before", sa.Integer(), nullable=False),
        sa.Column("white_elo_after", sa.Integer(), nullable=True),
        sa.Column("black_elo_after", sa.Integer(), nullable=True),
        sa.Column("white_reward", sa.Integer(), nullable=True),
        sa.Column("black_reward", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'finished', 'aborted')", name=op.f("ck_games_status_whitelist")),
        sa.CheckConstraint("draw_offer_by IN ('white', 'black')", name=op.f("ck_games_draw_offer_by_whitelist")),
        sa.CheckConstraint("result IN ('white', 'black', 'draw')", name=op.f("ck_games_result_whitelist")),
        sa.CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('checkmate', 'stalemate', 'insufficient_material', "
            "'fifty_move', 'threefold', 'resign', 'timeout', 'timeout_vs_insufficient', 'agreement', "
            "'abort', 'abort_no_first_move')",
            name=op.f("ck_games_end_reason_whitelist"),
        ),
        sa.ForeignKeyConstraint(["white_id"], ["users.id"], name=op.f("fk_games_white_id_users")),
        sa.ForeignKeyConstraint(["black_id"], ["users.id"], name=op.f("fk_games_black_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
    )
    op.create_index(
        "ix_games_white_id_finished_at",
        "games",
        [sa.text("white_id"), sa.text("finished_at DESC")],
    )
    op.create_index(
        "ix_games_black_id_finished_at",
        "games",
        [sa.text("black_id"), sa.text("finished_at DESC")],
    )
    op.create_index("ix_games_status", "games", ["status"])

    op.create_table(
        "active_players",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_active_players_user_id_users")),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_active_players_game_id_games")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_active_players")),
    )

    op.create_table(
        "game_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("fen_after", sa.Text(), nullable=False),
        sa.Column("white_ms", sa.BigInteger(), nullable=True),
        sa.Column("black_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("actor IN ('white', 'black', 'system')", name=op.f("ck_game_events_actor_whitelist")),
        sa.CheckConstraint(
            "kind IN ('move', 'dep', 'resign', 'draw_offer', 'draw_accept', 'draw_decline', "
            "'abort', 'flag', 'game_over')",
            name=op.f("ck_game_events_kind_whitelist"),
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_game_events_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_events")),
        sa.UniqueConstraint("game_id", "seq", name=op.f("uq_game_events_game_id_seq")),
    )

    op.create_table(
        "invites",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("creator_id", sa.BigInteger(), nullable=False),
        sa.Column("time_control", sa.Text(), nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", pg.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("game_id", pg.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], name=op.f("fk_invites_creator_id_users")),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_invites_game_id_games")),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_invites")),
    )

    op.create_table(
        "rolls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("chance", sa.Numeric(10, 8), nullable=True),
        sa.Column("roll_value", sa.Double(), nullable=False),
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("outcome", JSONB(), nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('dep', 'case_open', 'upgrade')", name=op.f("ck_rolls_kind_whitelist")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_rolls_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rolls")),
    )
    op.create_index(
        "ix_rolls_user_id_created_at",
        "rolls",
        [sa.text("user_id"), sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_rolls_user_id_created_at", table_name="rolls")
    op.drop_table("rolls")
    op.drop_table("invites")
    op.drop_table("game_events")
    op.drop_table("active_players")
    op.drop_index("ix_games_status", table_name="games")
    op.drop_index("ix_games_black_id_finished_at", table_name="games")
    op.drop_index("ix_games_white_id_finished_at", table_name="games")
    op.drop_table("games")
