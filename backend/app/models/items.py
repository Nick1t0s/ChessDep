from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ItemSet(Base):
    __tablename__ = "item_sets"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'released', 'retired')", name="status_whitelist"),
        Index(
            "uq_item_sets_single_base",
            "is_base",
            unique=True,
            postgresql_where=text("is_base"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )
    is_base: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (Index("ix_collections_set_id", "set_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_sets.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ItemDef(Base):
    __tablename__ = "item_defs"
    __table_args__ = (
        CheckConstraint("kind IN ('piece', 'board')", name="kind_whitelist"),
        CheckConstraint("side IS NULL OR side IN ('w', 'b')", name="side_whitelist"),
        CheckConstraint(
            "piece_type IS NULL OR piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
            name="piece_type_whitelist",
        ),
        CheckConstraint(
            "(kind = 'piece' AND collection_id IS NOT NULL AND side IS NOT NULL AND piece_type IS NOT NULL) "
            "OR (kind = 'board' AND collection_id IS NULL AND side IS NULL AND piece_type IS NULL)",
            name="kind_shape",
        ),
        CheckConstraint(
            "rarity IN ('common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic')",
            name="rarity_whitelist",
        ),
        CheckConstraint("value > 0", name="value_positive"),
        UniqueConstraint(
            "collection_id", "side", "piece_type",
            name="uq_item_defs_collection_id_side_piece_type",
        ),
        Index("ix_item_defs_collection_id", "collection_id"),
        Index("ix_item_defs_set_id", "set_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_sets.id"), nullable=False
    )
    collection_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("collections.id")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str | None] = mapped_column(CHAR(1))
    piece_type: Mapped[str | None] = mapped_column(CHAR(1))
    rarity: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    asset: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_upgrade_target: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(
            "source IN ('case', 'upgrade', 'admin_grant', 'base', 'shop', 'daily_reward')",
            name="source_whitelist",
        ),
        CheckConstraint("status IN ('owned', 'listed', 'burned')", name="status_whitelist"),
        CheckConstraint("wear IS NULL OR (wear >= 0 AND wear < 1)", name="wear_range"),
        CheckConstraint("(item_def_id IS NULL) <> (case_id IS NULL)", name="one_kind"),
        Index("ix_inventory_items_user_id_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    item_def_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("item_defs.id"))
    case_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cases.id"))
    wear: Mapped[float | None] = mapped_column(REAL)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="owned", server_default="owned"
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    burned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Loadout(Base):
    __tablename__ = "loadouts"
    __table_args__ = (
        CheckConstraint(
            "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK', 'board')",
            name="slot_whitelist",
        ),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    slot: Mapped[str] = mapped_column(Text, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_items.id"), nullable=False, unique=True
    )


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("status IN ('draft', 'on_sale', 'off_sale')", name="status_whitelist"),
        CheckConstraint("kind IN ('set', 'collection', 'custom')", name="kind_whitelist"),
        CheckConstraint(
            "(kind = 'set' AND set_id IS NOT NULL AND collection_id IS NULL) "
            "OR (kind = 'collection' AND collection_id IS NOT NULL AND set_id IS NULL) "
            "OR (kind = 'custom' AND set_id IS NULL AND collection_id IS NULL)",
            name="kind_ref",
        ),
        CheckConstraint("stock_limit IS NULL OR stock_limit > 0", name="stock_limit_positive"),
        CheckConstraint("sold_count >= 0", name="sold_count_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default="draft")
    set_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("item_sets.id"))
    collection_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("collections.id"))
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    stock_limit: Mapped[int | None] = mapped_column(Integer)
    sold_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    sale_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sale_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseDrop(Base):
    __tablename__ = "case_drops"
    __table_args__ = (CheckConstraint("weight > 0", name="weight_positive"),)

    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("cases.id"), primary_key=True)
    item_def_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_defs.id"), primary_key=True
    )
    weight: Mapped[int] = mapped_column(Integer, nullable=False)


class DailyRewardPool(Base):
    __tablename__ = "daily_reward_pool"
    __table_args__ = (CheckConstraint("weight > 0", name="weight_positive"),)

    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("cases.id"), primary_key=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)


class SkinImage(Base):
    """PNG-картинка скина; id — sha256 байт (docs/contracts-skins.md)."""

    __tablename__ = "skin_images"
    __table_args__ = (
        CheckConstraint("kind IN ('piece', 'board')", name="kind_whitelist"),
    )

    id: Mapped[str] = mapped_column(CHAR(64), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
