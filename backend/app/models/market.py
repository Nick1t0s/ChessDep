from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketListing(Base):
    __tablename__ = "market_listings"
    __table_args__ = (
        CheckConstraint("price BETWEEN 1 AND 10000000", name="price_range"),
        CheckConstraint("status IN ('active', 'sold', 'cancelled')", name="status_whitelist"),
        Index(
            "uq_market_listings_active_item",
            "item_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_market_listings_item_def_id_status_price", "item_def_id", "status", "price"),
        Index("ix_market_listings_seller_id_status", "seller_id", "status"),
        Index("ix_market_listings_status_created_at", "status", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_items.id"), nullable=False
    )
    item_def_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("item_defs.id"), nullable=False
    )
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    buyer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    fee: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemTransfer(Base):
    __tablename__ = "item_transfers"
    __table_args__ = (
        CheckConstraint("kind IN ('market', 'gift')", name="kind_whitelist"),
        CheckConstraint("length(note) <= 140", name="note_length"),
        Index(
            "ix_item_transfers_to_user_id_kind_created_at",
            "to_user_id",
            "kind",
            text("created_at DESC"),
        ),
        Index(
            "ix_item_transfers_from_user_id_kind_created_at",
            "from_user_id",
            "kind",
            text("created_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("inventory_items.id"), nullable=False
    )
    from_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    seen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
