from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, constr

from app.schemas.market import ListingItemOut


class GiftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    item: ListingItemOut
    from_login: str
    to_login: str
    note: str | None
    seen: bool
    created_at: datetime


class GiftsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GiftOut]
    next_cursor: int | None


class GiftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    to_login: constr(min_length=1, max_length=64)  # type: ignore[valid-type]
    note: constr(max_length=140) | None = None  # type: ignore[misc]


class UnseenCountOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
