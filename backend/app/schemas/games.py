from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, constr

_UciPattern = constr(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
_SquarePattern = constr(pattern=r"^[a-h][1-8]$")


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uci: _UciPattern
    expected_version: int | None = None


class DepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    square: _SquarePattern
    target: Literal["N", "B", "R", "Q"]
    expected_version: int | None = None


class ActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = None


class TimeControlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_control: str


class PieceSquareOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    square: str
    piece: str
    color: str


class ClocksOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    white_ms: int
    black_ms: int
    running: str | None
    server_time_ms: int


class DepsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int
    white_used: int
    black_used: int
    used_this_turn: bool


class PlayerInfoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str
    elo: int
    loadout: dict[str, Any]


class GameStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int
    status: str
    time_control: str
    you: str
    turn: str
    ply: int
    board: list[PieceSquareOut]
    legal_moves: list[str]
    check_square: str | None
    last_action: dict[str, Any] | None
    clocks: ClocksOut
    deps: DepsOut
    draw_offer_by: str | None
    result: str | None
    end_reason: str | None
    players: dict[str, PlayerInfoOut]


class DepTargetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    piece: str
    chance: float
    chance_text: str
    allowed: bool
    reason: str | None = None


class DepPieceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    square: str
    piece: str
    targets: list[DepTargetOut]


class DepOptionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    unavailable_reason: str | None = None
    deps_left: int
    pieces: list[DepPieceOut]


class DepEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    by: str
    square: str
    from_: str = Field(alias="from")
    to: str
    success: bool
    chance: float
    roll_value: float


class EloDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    white: int
    black: int


class Rewards(BaseModel):
    model_config = ConfigDict(extra="forbid")

    white: int
    black: int


class GameOver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: str | None
    end_reason: str
    elo_delta: EloDelta | None
    rewards: Rewards


class DepResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    success: bool
    square: str
    from_: str = Field(alias="from")
    to: str
    chance: float
    chance_text: str
    roll_value: float
    roll_id: int
    state: GameStateOut


class GameHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    opponent_login: str
    color: str
    result: str | None
    end_reason: str | None
    time_control: str
    finished_at: datetime
    elo_delta: int | None


class GamesHistoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GameHistoryItem]
    next_before: str | None
