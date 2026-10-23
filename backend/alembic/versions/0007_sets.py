"""sets, boards, item-cases, shop, daily reward pool; item contract v3

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import sqlalchemy.dialects.postgresql as pg
from sqlalchemy.dialects.postgresql import JSONB

from app.seed_data import seed_rows

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_TO_CLEAR: tuple[str, ...] = (
    "item_transfers",
    "market_listings",
    "loadouts",
    "inventory_items",
    "case_drops",
    "cases",
    "item_defs",
    "collections",
)

_ITEM_SETS_COLUMNS = (
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("code", sa.Text(), nullable=False),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("description", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), server_default="draft", nullable=False),
    sa.Column("is_base", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    sa.Column(
        "created_at", pg.TIMESTAMP(timezone=True), server_default=sa.func.now(),
        nullable=False,
    ),
    sa.Column("released_at", pg.TIMESTAMP(timezone=True), nullable=True),
    sa.Column("retired_at", pg.TIMESTAMP(timezone=True), nullable=True),
)


def upgrade() -> None:
    for table in _TABLES_TO_CLEAR:
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.create_table(
        "item_sets",
        *_ITEM_SETS_COLUMNS,
        sa.CheckConstraint(
            "status IN ('draft', 'released', 'retired')",
            name=op.f("ck_item_sets_status_whitelist"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_sets")),
        sa.UniqueConstraint("code", name=op.f("uq_item_sets_code")),
    )
    op.create_index(
        op.f("uq_item_sets_single_base"),
        "item_sets",
        ["is_base"],
        unique=True,
        postgresql_where=sa.text("is_base"),
    )

    # collections: статусы переносятся в набор, коллекция принадлежит набору.
    op.drop_constraint(op.f("ck_collections_status_whitelist"), "collections", type_="check")
    op.drop_column("collections", "status")
    op.drop_column("collections", "released_at")
    op.drop_column("collections", "retired_at")
    op.add_column("collections", sa.Column("set_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        op.f("fk_collections_set_id_item_sets"),
        "collections",
        "item_sets",
        ["set_id"],
        ["id"],
    )
    op.create_index(op.f("ix_collections_set_id"), "collections", ["set_id"])

    # item_defs: kind ∈ {piece, board}, каждый скин принадлежит набору.
    op.add_column("item_defs", sa.Column("kind", sa.Text(), nullable=False))
    op.create_check_constraint(
        op.f("ck_item_defs_kind_whitelist"),
        "item_defs",
        "kind IN ('piece', 'board')",
    )
    op.add_column("item_defs", sa.Column("set_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        op.f("fk_item_defs_set_id_item_sets"),
        "item_defs",
        "item_sets",
        ["set_id"],
        ["id"],
    )
    op.create_index(op.f("ix_item_defs_set_id"), "item_defs", ["set_id"])
    op.alter_column("item_defs", "collection_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("item_defs", "side", existing_type=sa.CHAR(length=1), nullable=True)
    op.alter_column("item_defs", "piece_type", existing_type=sa.CHAR(length=1), nullable=True)
    op.drop_constraint(op.f("ck_item_defs_side_whitelist"), "item_defs", type_="check")
    op.create_check_constraint(
        op.f("ck_item_defs_side_whitelist"),
        "item_defs",
        "side IS NULL OR side IN ('w', 'b')",
    )
    op.drop_constraint(
        op.f("ck_item_defs_piece_type_whitelist"), "item_defs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_item_defs_piece_type_whitelist"),
        "item_defs",
        "piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
    )
    op.create_check_constraint(
        op.f("ck_item_defs_kind_shape"),
        "item_defs",
        "(kind = 'piece' AND collection_id IS NOT NULL AND side IS NOT NULL AND "
        "piece_type IS NOT NULL) OR (kind = 'board' AND collection_id IS NULL AND "
        "side IS NULL AND piece_type IS NULL)",
    )

    # cases: товар магазина, kind ∈ {set, collection, custom}, тираж и окно продажи.
    op.add_column("cases", sa.Column("kind", sa.Text(), nullable=False))
    op.add_column("cases", sa.Column("set_id", sa.Integer(), nullable=True))
    op.add_column("cases", sa.Column("collection_id", sa.Integer(), nullable=True))
    op.add_column("cases", sa.Column("stock_limit", sa.Integer(), nullable=True))
    op.add_column(
        "cases",
        sa.Column("sold_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "cases", sa.Column("sale_starts_at", pg.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "cases", sa.Column("sale_ends_at", pg.TIMESTAMP(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_cases_kind_whitelist"),
        "cases",
        "kind IN ('set', 'collection', 'custom')",
    )
    op.create_check_constraint(
        op.f("ck_cases_kind_ref"),
        "cases",
        "(kind = 'set' AND set_id IS NOT NULL AND collection_id IS NULL) OR "
        "(kind = 'collection' AND collection_id IS NOT NULL AND set_id IS NULL) OR "
        "(kind = 'custom' AND set_id IS NULL AND collection_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_cases_stock_limit_positive"),
        "cases",
        "stock_limit IS NULL OR stock_limit > 0",
    )
    op.create_check_constraint(
        op.f("ck_cases_sold_count_nonnegative"),
        "cases",
        "sold_count >= 0",
    )
    op.create_foreign_key(
        op.f("fk_cases_set_id_item_sets"),
        "cases",
        "item_sets",
        ["set_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_cases_collection_id_collections"),
        "cases",
        "collections",
        ["collection_id"],
        ["id"],
    )
    op.drop_constraint(op.f("ck_cases_status_whitelist"), "cases", type_="check")
    op.create_check_constraint(
        op.f("ck_cases_status_whitelist"),
        "cases",
        "status IN ('draft', 'on_sale', 'off_sale')",
    )
    op.alter_column("cases", "status", existing_type=sa.Text(), server_default="draft")

    # inventory_items: кейс-предмему можно держать в инвентаре; базовые скины.
    op.alter_column("inventory_items", "item_def_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("inventory_items", "wear", existing_type=sa.REAL(), nullable=True)
    op.add_column("inventory_items", sa.Column("case_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_inventory_items_case_id_cases"),
        "inventory_items",
        "cases",
        ["case_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_inventory_items_one_kind"),
        "inventory_items",
        "(item_def_id IS NULL) <> (case_id IS NULL)",
    )
    op.drop_constraint(
        op.f("ck_inventory_items_wear_range"), "inventory_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inventory_items_wear_range"),
        "inventory_items",
        "wear IS NULL OR (wear >= 0 AND wear < 1)",
    )
    op.drop_constraint(
        op.f("ck_inventory_items_source_whitelist"), "inventory_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inventory_items_source_whitelist"),
        "inventory_items",
        "source IN ('case', 'upgrade', 'admin_grant', 'base', 'shop', 'daily_reward')",
    )

    # loadouts: 12 фигурных слотов + доска.
    op.drop_constraint(op.f("ck_loadouts_slot_whitelist"), "loadouts", type_="check")
    op.create_check_constraint(
        op.f("ck_loadouts_slot_whitelist"),
        "loadouts",
        "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK', 'board')",
    )

    # market_listings: на маркет тоже выставляются кейсы-предметы.
    op.alter_column("market_listings", "item_def_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("market_listings", sa.Column("case_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_market_listings_case_id_cases"),
        "market_listings",
        "cases",
        ["case_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_market_listings_one_kind"),
        "market_listings",
        "(item_def_id IS NULL) <> (case_id IS NULL)",
    )
    op.create_index(
        op.f("ix_market_listings_case_id_status_price"),
        "market_listings",
        ["case_id", "status", "price"],
    )

    # daily_reward_pool: пул кейсов еженедельной награды (случайный выбор по весам).
    op.create_table(
        "daily_reward_pool",
        sa.Column("case_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "weight > 0", name=op.f("ck_daily_reward_pool_weight_positive")
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_daily_reward_pool_case_id_cases")
        ),
        sa.PrimaryKeyConstraint("case_id", name=op.f("pk_daily_reward_pool")),
    )

    # users: бонус по кулдауну заменён наградой за победы.
    op.drop_column("users", "last_daily_bonus_at")
    op.add_column("users", sa.Column("last_daily_reward_on", sa.Date(), nullable=True))

    op.drop_constraint(op.f("ck_rolls_kind_whitelist"), "rolls", type_="check")
    op.create_check_constraint(
        op.f("ck_rolls_kind_whitelist"),
        "rolls",
        "kind IN ('dep', 'case_open', 'upgrade', 'daily_reward')",
    )

    op.execute(
        sa.text("DELETE FROM settings WHERE key IN ('daily_bonus', 'daily_bonus_cooldown_h')")
    )
    op.bulk_insert(
        _settings_table(),
        [{"key": "daily_reward_wins", "value": 3}],
    )

    rows = seed_rows()
    op.bulk_insert(_item_sets_table(), rows["item_sets"])
    op.bulk_insert(_collections_table(), rows["collections"])
    op.bulk_insert(_item_defs_table(), rows["item_defs"])
    op.bulk_insert(_cases_table(), rows["cases"])
    op.bulk_insert(_case_drops_table(), rows["case_drops"])
    op.bulk_insert(_daily_reward_pool_table(), rows["daily_reward_pool"])

    # После вставки с явными id сдвинуть последовательности, иначе следующая
    # автоинкрементная вставка упадёт на дубликате id.
    for table in ("item_sets", "collections", "item_defs", "cases"):
        op.execute(
            sa.text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))"
            )
        )

    # Выдать 13 базовых скинов каждому пользователю и сразу экипировать.
    op.execute(
        sa.text(
            "INSERT INTO inventory_items "
            "(user_id, item_def_id, wear, status, source, created_at, acquired_at) "
            "SELECT u.id, d.id, 0, 'owned', 'base', now(), now() "
            "FROM users u CROSS JOIN item_defs d WHERE d.id BETWEEN 1 AND 13"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO loadouts (user_id, slot, inventory_item_id) "
            "SELECT i.user_id, "
            "CASE WHEN d.kind = 'board' THEN 'board' ELSE d.side || d.piece_type END, "
            "i.id FROM inventory_items i JOIN item_defs d ON d.id = i.item_def_id "
            "WHERE i.source = 'base'"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM daily_reward_pool"))
    for table in _TABLES_TO_CLEAR:
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.execute(sa.text("DELETE FROM rolls WHERE kind = 'daily_reward'"))
    op.drop_constraint(op.f("ck_rolls_kind_whitelist"), "rolls", type_="check")
    op.create_check_constraint(
        op.f("ck_rolls_kind_whitelist"),
        "rolls",
        "kind IN ('dep', 'case_open', 'upgrade')",
    )

    op.drop_column("users", "last_daily_reward_on")
    op.add_column(
        "users",
        sa.Column("last_daily_bonus_at", pg.TIMESTAMP(timezone=True), nullable=True),
    )

    op.drop_table("daily_reward_pool")

    op.drop_index(
        op.f("ix_market_listings_case_id_status_price"), table_name="market_listings"
    )
    op.drop_constraint(
        op.f("ck_market_listings_one_kind"), "market_listings", type_="check"
    )
    op.drop_constraint(
        op.f("fk_market_listings_case_id_cases"), "market_listings", type_="foreignkey"
    )
    op.drop_column("market_listings", "case_id")
    op.alter_column("market_listings", "item_def_id", existing_type=sa.Integer(), nullable=False)

    op.drop_constraint(op.f("ck_loadouts_slot_whitelist"), "loadouts", type_="check")
    op.create_check_constraint(
        op.f("ck_loadouts_slot_whitelist"),
        "loadouts",
        "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK')",
    )

    op.drop_constraint(
        op.f("ck_inventory_items_source_whitelist"), "inventory_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inventory_items_source_whitelist"),
        "inventory_items",
        "source IN ('case', 'upgrade', 'admin_grant')",
    )
    op.drop_constraint(
        op.f("ck_inventory_items_wear_range"), "inventory_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_inventory_items_wear_range"),
        "inventory_items",
        "wear >= 0 AND wear < 1",
    )
    op.drop_constraint(
        op.f("ck_inventory_items_one_kind"), "inventory_items", type_="check"
    )
    op.drop_constraint(
        op.f("fk_inventory_items_case_id_cases"), "inventory_items", type_="foreignkey"
    )
    op.drop_column("inventory_items", "case_id")
    op.alter_column("inventory_items", "item_def_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("inventory_items", "wear", existing_type=sa.REAL(), nullable=False)

    op.drop_constraint(op.f("ck_cases_kind_ref"), "cases", type_="check")
    op.drop_constraint(op.f("ck_cases_kind_whitelist"), "cases", type_="check")
    op.drop_constraint(
        op.f("ck_cases_stock_limit_positive"), "cases", type_="check"
    )
    op.drop_constraint(
        op.f("ck_cases_sold_count_nonnegative"), "cases", type_="check"
    )
    op.drop_constraint(
        op.f("fk_cases_set_id_item_sets"), "cases", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_cases_collection_id_collections"), "cases", type_="foreignkey"
    )
    op.drop_column("cases", "sale_ends_at")
    op.drop_column("cases", "sale_starts_at")
    op.drop_column("cases", "sold_count")
    op.drop_column("cases", "stock_limit")
    op.drop_column("cases", "collection_id")
    op.drop_column("cases", "set_id")
    op.drop_column("cases", "kind")

    op.drop_index(op.f("ix_collections_set_id"), table_name="collections")
    op.drop_constraint(
        op.f("fk_collections_set_id_item_sets"), "collections", type_="foreignkey"
    )
    op.drop_column("collections", "set_id")

    # item_defs: обратно к v1-схеме (kind, отказ от nullable) — до правок whitelist'ов.
    op.drop_constraint(op.f("ck_item_defs_kind_shape"), "item_defs", type_="check")
    op.drop_constraint(op.f("ck_item_defs_kind_whitelist"), "item_defs", type_="check")
    op.drop_index(op.f("ix_item_defs_set_id"), table_name="item_defs")
    op.drop_constraint(
        op.f("fk_item_defs_set_id_item_sets"), "item_defs", type_="foreignkey"
    )
    op.drop_column("item_defs", "set_id")
    op.drop_column("item_defs", "kind")
    op.drop_constraint(op.f("ck_item_defs_side_whitelist"), "item_defs", type_="check")
    op.create_check_constraint(
        op.f("ck_item_defs_side_whitelist"), "item_defs", "side IN ('w', 'b')"
    )
    op.drop_constraint(
        op.f("ck_item_defs_piece_type_whitelist"), "item_defs", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_item_defs_piece_type_whitelist"),
        "item_defs",
        "piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
    )
    op.alter_column("item_defs", "collection_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("item_defs", "side", existing_type=sa.CHAR(length=1), nullable=False)
    op.alter_column("item_defs", "piece_type", existing_type=sa.CHAR(length=1), nullable=False)

    op.add_column(
        "collections",
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_collections_status_whitelist"),
        "collections",
        "status IN ('draft', 'released', 'retired')",
    )
    op.add_column(
        "collections", sa.Column("released_at", pg.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "collections", sa.Column("retired_at", pg.TIMESTAMP(timezone=True), nullable=True)
    )

    op.execute(
        sa.text("DELETE FROM settings WHERE key = 'daily_reward_wins'")
    )
    op.bulk_insert(
        _settings_table(),
        [
            {"key": "daily_bonus", "value": 200},
            {"key": "daily_bonus_cooldown_h", "value": 24},
        ],
    )

    op.drop_index(op.f("uq_item_sets_single_base"), table_name="item_sets")
    op.drop_table("item_sets")


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


def _item_sets_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "item_sets",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("is_base", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("released_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retired_at", pg.TIMESTAMP(timezone=True), nullable=True),
    )


def _collections_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "collections",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", pg.TIMESTAMP(timezone=True), nullable=True),
    )


def _item_defs_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "item_defs",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("side", sa.CHAR(length=1), nullable=True),
        sa.Column("piece_type", sa.CHAR(length=1), nullable=True),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("asset", JSONB(), nullable=False),
        sa.Column(
            "is_upgrade_target", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("created_at", pg.TIMESTAMP(timezone=True), nullable=True),
    )


def _cases_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "cases",
        metadata,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=True),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("sort", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stock_limit", sa.Integer(), nullable=True),
        sa.Column("sold_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sale_starts_at", pg.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("sale_ends_at", pg.TIMESTAMP(timezone=True), nullable=True),
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


def _daily_reward_pool_table() -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(
        "daily_reward_pool",
        metadata,
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
    )
