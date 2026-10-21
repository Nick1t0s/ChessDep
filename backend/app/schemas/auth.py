from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, constr

T = TypeVar("T")

_LoginPattern = constr(pattern=r"^[A-Za-z0-9_-]{3,16}$")


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: _LoginPattern
    email: EmailStr
    password: constr(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: constr(min_length=1, max_length=64)
    password: constr(min_length=1, max_length=128)


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: constr(min_length=1, max_length=128)
    new_password: constr(min_length=8, max_length=128)


class MeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    login: str
    role: str
    balance: int
    elo: int
    daily_bonus_available_at: datetime | None


class LedgerItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    delta: int
    balance_after: int
    reason: str
    ref: str | None
    created_at: datetime


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    next_cursor: int | None


class DailyBonusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance: int
    next_available_at: datetime
