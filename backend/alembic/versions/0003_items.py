"""items: collections, item_defs, inventory_items, loadouts, cases, case_drops; genesis seed

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

import sqlalchemy.dialects.postgresql as pg

from app.seed_data import genesis_rows

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("released_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retired_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'released', 'retired')",
            name=op.f("ck_collections_status_whitelist"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("code", name=op.f("uq_collections_code")),
    )

    op.create_table(
        "item_defs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("piece_type", sa.CHAR(length=1), nullable=True),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("asset", JSONB(), nullable=False),
        sa.Column(
            "is_upgrade_target", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kind = 'piece_skin') = (piece_type IS NOT NULL)",
            name=op.f("ck_item_defs_kind_piece_type_consistency"),
        ),
        sa.CheckConstraint(
            "kind IN ('piece_skin', 'board_skin')",
            name=op.f("ck_item_defs_kind_whitelist"),
        ),
        sa.CheckConstraint(
            "piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
            name=op.f("ck_item_defs_piece_type_whitelist"),
        ),
        sa.CheckConstraint(
            "rarity IN ('common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic')",
            name=op.f("ck_item_defs_rarity_whitelist"),
        ),
        sa.CheckConstraint("value > 0", name=op.f("ck_item_defs_value_positive")),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"],
            name=op.f("fk_item_defs_collection_id_collections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_defs")),
        sa.UniqueConstraint("code", name=op.f("uq_item_defs_code")),
    )
    op.create_index(op.f("ix_item_defs_collection_id"), "item_defs", ["collection_id"])

    op.create_table(
        "inventory_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("item_def_id", sa.Integer(), nullable=False),
        sa.Column("wear", sa.REAL(), nullable=False),
        sa.Column("status", sa.Text(), server_default="owned", nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("acquired_at", pg.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("burned_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('case', 'upgrade', 'admin_grant')",
            name=op.f("ck_inventory_items_source_whitelist"),
        ),
        sa.CheckConstraint(
            "status IN ('owned', 'listed', 'burned')",
            name=op.f("ck_inventory_items_status_whitelist"),
        ),
        sa.CheckConstraint(
            "wear >= 0 AND wear < 1", name=op.f("ck_inventory_items_wear_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_inventory_items_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["item_def_id"], ["item_defs.id"],
            name=op.f("fk_inventory_items_item_def_id_item_defs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_items")),
    )
    op.create_index(
        "ix_inventory_items_user_id_status", "inventory_items", ["user_id", "status"]
    )

    op.create_table(
        "loadouts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("inventory_item_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "slot IN ('P', 'N', 'B', 'R', 'Q', 'K', 'board')",
            name=op.f("ck_loadouts_slot_whitelist"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_loadouts_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"],
            name=op.f("fk_loadouts_inventory_item_id_inventory_items"),
        ),
        sa.PrimaryKeyConstraint("user_id", "slot", name=op.f("pk_loadouts")),
        sa.UniqueConstraint("inventory_item_id", name=op.f("uq_loadouts_inventory_item_id")),
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("price > 0", name=op.f("ck_cases_price_positive")),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"],
            name=op.f("fk_cases_collection_id_collections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("code", name=op.f("uq_cases_code")),
    )
    op.create_index(op.f("ix_cases_collection_id"), "cases", ["collection_id"])

    op.create_table(
        "case_drops",
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("item_def_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.CheckConstraint("weight > 0", name=op.f("ck_case_drops_weight_positive")),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_case_drops_case_id_cases")
        ),
        sa.ForeignKeyConstraint(
            ["item_def_id"], ["item_defs.id"],
            name=op.f("fk_case_drops_item_def_id_item_defs"),
        ),
        sa.PrimaryKeyConstraint("case_id", "item_def_id", name=op.f("pk_case_drops")),
    )

    op.bulk_insert(_settings_table(), _new_setting_rows())

    rows = genesis_rows()
    op.bulk_insert(_collections_table(), rows["collections"])
    op.bulk_insert(_item_defs_table(), rows["item_defs"])
    op.bulk_insert(_cases_table(), rows["cases"])
    op.bulk_insert(_case_drops_table(), rows["case_drops"])

    # После вставки с явными id сдвинуть последовательности, иначе следующая
    # автоинкрементная вставка упадёт на дубликате id.
    for table in ("collections", "item_defs", "cases"):
        op.execute(
            sa.text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))"
            )
        )


def downgrade() -> None:
    op.drop_table("case_drops")
    op.drop_index(op.f("ix_cases_collection_id"), table_name="cases")
    op.drop_table("cases")
    op.drop_table("loadouts")
    op.drop_index("ix_inventory_items_user_id_status", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_index(op.f("ix_item_defs_collection_id"), table_name="item_defs")
    op.drop_table("item_defs")
    op.drop_table("collections")
    op.execute(
        sa.text(
            "DELETE FROM settings WHERE key IN "
            "('rarity_weights', 'market_fee', 'market_max_listings', 'trade_hold_hours')"
        )
    )


_NEW_SETTINGS: list[tuple[str, object]] = [
    (
        "rarity_weights",
        {"common": 7992, "uncommon": 1598, "rare": 320, "epic": 64, "legendary": 20, "mythic": 6},
    ),
    ("market_fee", 0.05),
    ("market_max_listings", 50),
    ("trade_hold_hours", 0),
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


def _new_setting_rows() -> list[dict[str, object]]:
    return [{"key": key, "value": value} for key, value in _NEW_SETTINGS]


def _collections_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "collections",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("released_at", pg.TIMESTAMP(timezone=True), nullable=True),
    )


def _item_defs_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "item_defs",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("piece_type", sa.CHAR(length=1), nullable=True),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("asset", JSONB(), nullable=False),
        sa.Column(
            "is_upgrade_target", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )


def _cases_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "cases",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
    )


def _case_drops_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "case_drops",
        metadata,
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("item_def_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
    )
