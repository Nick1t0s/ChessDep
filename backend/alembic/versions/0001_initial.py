"""initial

Revision ID: 0001
Revises:
Create Date: 2026-10-21

"""
import sqlalchemy as sa
from alembic import op
from collections.abc import Sequence
from sqlalchemy.dialects.postgresql import JSONB

import sqlalchemy.dialects.postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("login", pg.CITEXT(), nullable=False),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        sa.Column("is_banned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("balance", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("elo", sa.Integer(), server_default="1200", nullable=False),
        sa.Column("last_daily_bonus_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("balance >= 0", name=op.f("ck_users_balance_nonnegative")),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role_whitelist")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("login", name=op.f("uq_users_login")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", pg.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ip", pg.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])

    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_settings_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )

    op.create_table(
        "ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason IN ('signup_bonus', 'daily_bonus', 'game_win', 'game_draw', "
            "'case_purchase', 'admin_adjust')",
            name=op.f("ck_ledger_reason_whitelist"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_ledger_user_id_users")),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_ledger_actor_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger")),
    )
    op.create_index(
        "ix_ledger_user_id_created_at",
        "ledger",
        [sa.text("user_id"), sa.text("created_at DESC")],
    )

    op.create_table(
        "admin_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["users.id"], name=op.f("fk_admin_audit_admin_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit")),
    )

    op.bulk_insert(_settings_table(), _seed_rows())


def downgrade() -> None:
    op.drop_table("admin_audit")
    op.drop_index("ix_ledger_user_id_created_at", table_name="ledger")
    op.drop_table("ledger")
    op.drop_table("settings")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")


_SETTINGS_DEFAULTS: list[tuple[str, object]] = [
    ("starting_balance", 1000),
    ("daily_bonus", 200),
    ("daily_bonus_cooldown_h", 24),
    ("game_win_reward", 100),
    ("game_draw_reward", 30),
    ("reward_min_plies", 10),
    ("reward_games_per_day", 20),
    ("dep_multiplier", 1.0),
    ("upgrade_edge", 0.05),
    ("upgrade_min_chance", 0.01),
    ("upgrade_max_chance", 0.80),
    ("upgrade_max_inputs", 10),
    ("time_controls", ["3+2", "5+0", "10+0"]),
    ("abort_first_move_s", 30),
]


def _settings_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "settings",
        metadata,
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
    )


def _seed_rows() -> list[dict[str, object]]:
    return [{"key": key, "value": value} for key, value in _SETTINGS_DEFAULTS]
