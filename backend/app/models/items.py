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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'released', 'retired')", name="status_whitelist"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemDef(Base):
    __tablename__ = "item_defs"
    __table_args__ = (
        CheckConstraint("side IN ('w', 'b')", name="side_whitelist"),
        CheckConstraint(
            "piece_type IN ('P', 'N', 'B', 'R', 'Q', 'K')",
            name="piece_type_whitelist",
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("collections.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    piece_type: Mapped[str] = mapped_column(CHAR(1), nullable=False)
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
        CheckConstraint("source IN ('case', 'upgrade', 'admin_grant')", name="source_whitelist"),
        CheckConstraint("status IN ('owned', 'listed', 'burned')", name="status_whitelist"),
        CheckConstraint("wear >= 0 AND wear < 1", name="wear_range"),
        Index("ix_inventory_items_user_id_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    item_def_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_defs.id"), nullable=False
    )
    wear: Mapped[float] = mapped_column(REAL, nullable=False)
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
            "slot IN ('wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK')",
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
        CheckConstraint("status IN ('draft', 'active', 'closed')", name="status_whitelist"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default="draft")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class CaseDrop(Base):
    __tablename__ = "case_drops"
    __table_args__ = (CheckConstraint("weight > 0", name="weight_positive"),)

    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("cases.id"), primary_key=True)
    item_def_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_defs.id"), primary_key=True
    )
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
