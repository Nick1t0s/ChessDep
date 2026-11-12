from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TradeHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    item_id: int
    item_def_id: int
    item_name: str
    direction: Literal["buy", "sell"]
    price: int
    fee: int
    net: int
    created_at: datetime


class TradeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sold_count: int
    bought_count: int
    gross_sales: int
    fees: int
    net_sales: int
    total_spent: int


class TradeHistoryPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TradeHistoryItem]
    next_cursor: int | None
    summary: TradeSummary
