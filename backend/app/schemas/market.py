from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.items import ItemDefOut


class ListingItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    item_def: ItemDefOut = Field(alias="def")
    wear: float
    exterior: str


class ListingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    price: int
    status: str
    created_at: datetime
    closed_at: datetime | None
    seller_login: str
    mine: bool
    item: ListingItemOut | None


class MarketStatsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_count: int
    min_price: int | None
    last_sale_price: int | None


class DefSaleOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: int
    closed_at: datetime


class DefMarketOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_def: ItemDefOut = Field(alias="def")
    stats: MarketStatsOut
    listings: list[ListingOut]
    sales: list[DefSaleOut]


class BrowseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingOut]
    total: int


class ListingCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    price: int = Field(ge=1, le=10_000_000)
