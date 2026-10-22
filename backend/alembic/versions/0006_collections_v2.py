"""collections v2: drop all items, rebuild schema for 12-piece collections, new genesis seed

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

import sqlalchemy.dialects.postgresql as pg

from app.seed_data import genesis_rows

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in (
        "item_transfers",
        "market_listings",
        "loadouts",
        "inventory_items",
        "case_drops",
        "cases",
        "item_defs",
        "collections",
    ):
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.drop_constraint(
        op.f("ck_item_defs_kind_piece_type_consistency"), "item_defs", type_="check"
    )
    op.drop_constraint(op.f("ck_item_defs_kind_whitelist"), "item_defs", type_="check")
    op.drop_constraint(
        op.f("ck_item_defs_piece_type_whitelist"), "item_defs", type_="check"
    )
    op.drop_column("item_defs", "kind")
    op.add_column("item_defs", sa.Column("side", sa.CHAR(length=1), nullable=False))
    op.alter_column(
        "item_defs", "piece_type", existing_type=sa.CHAR(length=1), nullable=False
    )
    op.create_check_constraint(
        op.f("ck_item_defs_side_whitelist"), "item_defs", "side IN ('w', 'b')"
    )
    op.create_check_constraint(
        op.f("ck_item_defs_piece_type_whitelist"),
        "item_defs",
        "piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
    )
    op.create_unique_constraint(
        op.f("uq_item_defs_collection_id_side_piece_type"),
        "item_defs",
        ["collection_id", "side", "piece_type"],
    )

    op.drop_index(op.f("ix_cases_collection_id"), table_name="cases")
    op.drop_constraint(
        op.f("fk_cases_collection_id_collections"), "cases", type_="foreignkey"
    )
    op.drop_column("cases", "collection_id")
    op.drop_column("cases", "is_active")
    op.add_column(
        "cases",
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_cases_status_whitelist"),
        "cases",
        "status IN ('draft', 'active', 'closed')",
    )

    op.drop_constraint(op.f("ck_loadouts_slot_whitelist"), "loadouts", type_="check")
    op.create_check_constraint(
        op.f("ck_loadouts_slot_whitelist"),
        "loadouts",
        "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK')",
    )

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
    for table in (
        "item_transfers",
        "market_listings",
        "loadouts",
        "inventory_items",
        "case_drops",
        "cases",
        "item_defs",
        "collections",
    ):
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.drop_constraint(op.f("ck_loadouts_slot_whitelist"), "loadouts", type_="check")
    op.create_check_constraint(
        op.f("ck_loadouts_slot_whitelist"),
        "loadouts",
        "slot IN ('P', 'N', 'B', 'R', 'Q', 'K', 'board')",
    )

    op.drop_constraint(
        op.f("ck_cases_status_whitelist"), "cases", type_="check"
    )
    op.drop_column("cases", "status")
    op.add_column("cases", sa.Column("collection_id", sa.Integer(), nullable=False))
    op.add_column(
        "cases",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_cases_collection_id_collections"),
        "cases",
        "collections",
        ["collection_id"],
        ["id"],
    )
    op.create_index(op.f("ix_cases_collection_id"), "cases", ["collection_id"])

    op.drop_constraint(
        op.f("uq_item_defs_collection_id_side_piece_type"), "item_defs", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_item_defs_side_whitelist"), "item_defs", type_="check"
    )
    op.drop_constraint(
        op.f("ck_item_defs_piece_type_whitelist"), "item_defs", type_="check"
    )
    op.drop_column("item_defs", "side")
    op.alter_column(
        "item_defs", "piece_type", existing_type=sa.CHAR(length=1), nullable=True
    )
    op.add_column("item_defs", sa.Column("kind", sa.Text(), nullable=False))
    op.create_check_constraint(
        op.f("ck_item_defs_kind_piece_type_consistency"),
        "item_defs",
        "(kind = 'piece_skin') = (piece_type IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_item_defs_kind_whitelist"),
        "item_defs",
        "kind IN ('piece_skin', 'board_skin')",
    )
    op.create_check_constraint(
        op.f("ck_item_defs_piece_type_whitelist"),
        "item_defs",
        "piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
    )


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
        sa.Column("side", sa.CHAR(length=1), nullable=False),
        sa.Column("piece_type", sa.CHAR(length=1), nullable=False),
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
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
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
