from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, constr, model_validator


class AdminUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    login: str
    email: str
    role: str
    is_banned: bool
    balance: int
    elo: int
    created_at: datetime
    active_game_id: str | None


class AdminLedgerItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    delta: int
    balance_after: int
    reason: str
    ref: str | None
    actor_id: int | None
    created_at: datetime


class AdminUserDetailOut(AdminUserOut):
    items_owned: int
    active_listings: int
    ledger: list[AdminLedgerItemOut]


class AdminUsersOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AdminUserOut]
    total: int


class BanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: constr(min_length=1, max_length=200)  # type: ignore[valid-type]


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: constr(min_length=1, max_length=200)  # type: ignore[valid-type]


class BalanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    comment: constr(min_length=1, max_length=200)  # type: ignore[valid-type]

    @model_validator(mode="after")
    def delta_not_zero(self) -> "BalanceIn":
        if self.delta == 0:
            raise ValueError("delta должен быть ≠ 0")
        return self


class SettingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    default: Any
    updated_at: datetime | None
    updated_by: int | None


class SettingPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any


class RollOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    user_id: int
    kind: str
    ref: str
    chance: float | None
    roll_value: float
    input: dict[str, Any]
    outcome: dict[str, Any]
    created_at: datetime


class GameEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    game_id: str
    seq: int
    ply: int
    actor: str
    kind: str
    payload: dict[str, Any]
    fen_after: str
    white_ms: int | None
    black_ms: int | None
    created_at: datetime


class AdminListingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    item_id: int
    item_def_id: int
    seller_id: int
    price: int
    status: str
    buyer_id: int | None
    fee: int | None
    created_at: datetime
    closed_at: datetime | None


class AuditOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    admin_id: int | None
    admin_login: str | None
    action: str
    target: str
    payload: Any
    created_at: datetime
