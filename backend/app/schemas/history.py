from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.games import PieceSquareOut


class EventPlayerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str
    elo: int


class EventGameOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    result: str | None
    end_reason: str | None
    time_control: str
    white: EventPlayerOut
    black: EventPlayerOut
    white_loadout: dict[str, Any]
    black_loadout: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None
    initial_board: list[PieceSquareOut]


class HistoryEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    ply: int
    kind: str
    actor: str
    payload: dict[str, Any]
    board: list[PieceSquareOut]
    check_square: str | None
    white_ms: int | None
    black_ms: int | None
    created_at: datetime


class GameEventsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: EventGameOut
    events: list[HistoryEventOut]


class ProfileGamesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    played: int
    wins: int
    draws: int
    losses: int


class ProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str
    elo: int
    created_at: datetime
    games: ProfileGamesOut
