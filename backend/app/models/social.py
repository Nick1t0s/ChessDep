from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_NOTIFICATION_KINDS = (
    "friend_request, friend_accepted, match_invite, market_sale, gift"
).replace(", ", "', '")


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint("user_low_id < user_high_id", name="user_order"),
        CheckConstraint(
            "requester_id = user_low_id OR requester_id = user_high_id",
            name="requester_in_pair",
        ),
        CheckConstraint("status IN ('pending', 'accepted')", name="status_whitelist"),
        UniqueConstraint("user_low_id", "user_high_id", name="uq_friendships_canonical_pair"),
        Index("ix_friendships_user_low_status", "user_low_id", "status"),
        Index("ix_friendships_user_high_status", "user_high_id", "status"),
        Index("ix_friendships_requester_status", "requester_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_low_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_high_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ('{_NOTIFICATION_KINDS}')",
            name="kind_whitelist",
        ),
        Index("ix_notifications_user_id_id", "user_id", "id"),
        Index("ix_notifications_user_unread", "user_id", "read"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    href: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InviteDelivery(Base):
    __tablename__ = "invite_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'declined')", name="invite_delivery_status_whitelist"),
        UniqueConstraint("code", "recipient_id", name="uq_invite_deliveries_code_recipient"),
        Index("ix_invite_deliveries_recipient_id", "recipient_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        Text, ForeignKey("invites.code", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSocialSettings(Base):
    __tablename__ = "user_social_settings"
    __table_args__ = (
        CheckConstraint("presence_mode IN ('online', 'dnd')", name="presence_mode_whitelist"),
        CheckConstraint("match_invites IN ('all', 'friends', 'none')", name="match_invites_whitelist"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    presence_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="online", server_default="online"
    )
    match_invites: Mapped[str] = mapped_column(
        Text, nullable=False, default="all", server_default="all"
    )
    notification_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        CheckConstraint("blocker_id != blocked_id", name="check_block_no_self"),
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_blocker_blocked"),
        Index("ix_user_blocks_blocker_id", "blocker_id"),
        Index("ix_user_blocks_blocked_id", "blocked_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    blocker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    blocked_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
