"""market: market_listings, item_transfers, ledger.reason extended

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

"""
import sqlalchemy as sa
from alembic import op
from collections.abc import Sequence

import sqlalchemy.dialects.postgresql as pg

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_REASONS = (
    "CHECK (reason IN ('signup_bonus', 'daily_bonus', 'game_win', 'game_draw', "
    "'case_purchase', 'admin_adjust'))"
)
_NEW_REASONS = (
    "CHECK (reason IN ('signup_bonus', 'daily_bonus', 'game_win', 'game_draw', "
    "'case_purchase', 'admin_adjust', 'market_buy', 'market_sale'))"
)


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE ledger DROP CONSTRAINT ck_ledger_reason_whitelist, "
        f"ADD CONSTRAINT ck_ledger_reason_whitelist {_NEW_REASONS}"
    )

    op.create_table(
        "market_listings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("item_def_id", sa.Integer(), nullable=False),
        sa.Column("seller_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("buyer_id", sa.BigInteger(), nullable=True),
        sa.Column("fee", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("closed_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "price BETWEEN 1 AND 10000000", name=op.f("ck_market_listings_price_range")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'sold', 'cancelled')",
            name=op.f("ck_market_listings_status_whitelist"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["inventory_items.id"],
            name=op.f("fk_market_listings_item_id_inventory_items"),
        ),
        sa.ForeignKeyConstraint(
            ["item_def_id"], ["item_defs.id"],
            name=op.f("fk_market_listings_item_def_id_item_defs"),
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"], ["users.id"], name=op.f("fk_market_listings_seller_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["buyer_id"], ["users.id"], name=op.f("fk_market_listings_buyer_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_listings")),
    )
    op.create_index(
        "uq_market_listings_active_item",
        "market_listings",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_market_listings_item_def_id_status_price",
        "market_listings",
        ["item_def_id", "status", "price"],
    )
    op.create_index(
        "ix_market_listings_seller_id_status", "market_listings", ["seller_id", "status"]
    )
    op.create_index(
        "ix_market_listings_status_created_at",
        "market_listings",
        [sa.text("status"), sa.text("created_at DESC")],
    )

    op.create_table(
        "item_transfers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("from_user_id", sa.BigInteger(), nullable=False),
        sa.Column("to_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("seen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("length(note) <= 140", name=op.f("ck_item_transfers_note_length")),
        sa.CheckConstraint(
            "kind IN ('market', 'gift')", name=op.f("ck_item_transfers_kind_whitelist")
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["inventory_items.id"],
            name=op.f("fk_item_transfers_item_id_inventory_items"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"], ["users.id"], name=op.f("fk_item_transfers_from_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"], ["users.id"], name=op.f("fk_item_transfers_to_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_transfers")),
    )
    op.create_index(
        "ix_item_transfers_to_user_id_kind_created_at",
        "item_transfers",
        [sa.text("to_user_id"), sa.text("kind"), sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_item_transfers_from_user_id_kind_created_at",
        "item_transfers",
        [sa.text("from_user_id"), sa.text("kind"), sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_item_transfers_from_user_id_kind_created_at", table_name="item_transfers"
    )
    op.drop_index("ix_item_transfers_to_user_id_kind_created_at", table_name="item_transfers")
    op.drop_table("item_transfers")
    op.drop_index("ix_market_listings_status_created_at", table_name="market_listings")
    op.drop_index("ix_market_listings_seller_id_status", table_name="market_listings")
    op.drop_index(
        "ix_market_listings_item_def_id_status_price", table_name="market_listings"
    )
    op.drop_index("uq_market_listings_active_item", table_name="market_listings")
    op.drop_table("market_listings")
    op.execute(
        f"ALTER TABLE ledger DROP CONSTRAINT ck_ledger_reason_whitelist, "
        f"ADD CONSTRAINT ck_ledger_reason_whitelist {_OLD_REASONS}"
    )
