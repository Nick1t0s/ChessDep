from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.items import CaseRefOut, ItemDefOut


class ListingItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    kind: Literal["skin", "case"]
    item_def: ItemDefOut | None = Field(default=None, alias="def")
    case: CaseRefOut | None = None
    wear: float | None = None
    exterior: str | None = None
    image: str | None = None


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


class CaseMarketOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: CaseRefOut
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


class SaleNoticeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: int
    name: str
    price: int
    payout: int
    buyer_login: str
    closed_at: datetime


class SalesUnseenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales: list[SaleNoticeOut]
    balance: int
