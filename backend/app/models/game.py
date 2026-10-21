import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_END_REASONS = (
    "checkmate, stalemate, insufficient_material, fifty_move, threefold, "
    "resign, timeout, timeout_vs_insufficient, agreement, abort, abort_no_first_move"
).replace(", ", "', '")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'finished', 'aborted')", name="status_whitelist"),
        CheckConstraint("draw_offer_by IN ('white', 'black')", name="draw_offer_by_whitelist"),
        CheckConstraint("result IN ('white', 'black', 'draw')", name="result_whitelist"),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('%s')" % _END_REASONS,
            name="end_reason_whitelist",
        ),
        Index("ix_games_white_id_finished_at", "white_id", text("finished_at DESC")),
        Index("ix_games_black_id_finished_at", "black_id", text("finished_at DESC")),
        Index("ix_games_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default="active")
    time_control: Mapped[str] = mapped_column(Text, nullable=False)
    base_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    inc_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    white_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    black_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    repetition: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    white_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    black_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    turn_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clock_running: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    abort_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dep_used_this_turn: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    white_deps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    black_deps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    draw_offer_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    white_last_offer_ply: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_last_offer_ply: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    white_loadout: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    black_loadout: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    white_elo_before: Mapped[int] = mapped_column(Integer, nullable=False)
    black_elo_before: Mapped[int] = mapped_column(Integer, nullable=False)
    white_elo_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_elo_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    white_reward: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_reward: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivePlayer(Base):
    __tablename__ = "active_players"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True, autoincrement=False
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.id"), nullable=False
    )


class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (
        CheckConstraint("actor IN ('white', 'black', 'system')", name="actor_whitelist"),
        CheckConstraint(
            "kind IN ('move', 'dep', 'resign', 'draw_offer', 'draw_accept', 'draw_decline', "
            "'abort', 'flag', 'game_over')",
            name="kind_whitelist",
        ),
        UniqueConstraint("game_id", "seq", name="uq_game_events_game_id_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.id"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fen_after: Mapped[str] = mapped_column(Text, nullable=False)
    white_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    black_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    time_control: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.id"), nullable=True
    )
