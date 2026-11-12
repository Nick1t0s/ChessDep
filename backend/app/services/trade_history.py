from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ItemDef
from app.models.market import MarketListing
from app.schemas.trade_history import TradeHistoryItem, TradeHistoryPageOut, TradeSummary


async def get_trade_history(
    db: AsyncSession,
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 20,
    item_def_id: int | None = None,
    direction: Literal["all", "buy", "sell"] = "all",
) -> TradeHistoryPageOut:
    limit = max(1, min(limit, 100))

    # 1. Summary across all directions and pages, scoped by user and optional item_def_id
    summary_stmt = (
        select(
            func.count().filter(MarketListing.seller_id == user_id).label("sold_count"),
            func.count().filter(MarketListing.buyer_id == user_id).label("bought_count"),
            func.coalesce(
                func.sum(MarketListing.price).filter(MarketListing.seller_id == user_id), 0
            ).label("gross_sales"),
            func.coalesce(
                func.sum(MarketListing.fee).filter(MarketListing.seller_id == user_id), 0
            ).label("fees"),
            func.coalesce(
                func.sum(MarketListing.price).filter(MarketListing.buyer_id == user_id), 0
            ).label("total_spent"),
        )
        .where(
            MarketListing.status == "sold",
            or_(MarketListing.seller_id == user_id, MarketListing.buyer_id == user_id),
        )
    )
    if item_def_id is not None:
        summary_stmt = summary_stmt.where(MarketListing.item_def_id == item_def_id)

    row = (await db.execute(summary_stmt)).one()
    sold_count = int(row.sold_count or 0)
    bought_count = int(row.bought_count or 0)
    gross_sales = int(row.gross_sales or 0)
    fees = int(row.fees or 0)
    total_spent = int(row.total_spent or 0)
    net_sales = gross_sales - fees

    summary = TradeSummary(
        sold_count=sold_count,
        bought_count=bought_count,
        gross_sales=gross_sales,
        fees=fees,
        net_sales=net_sales,
        total_spent=total_spent,
    )

    # 2. Paginated rows
    query = (
        select(MarketListing, ItemDef.name)
        .join(ItemDef, MarketListing.item_def_id == ItemDef.id)
        .where(MarketListing.status == "sold")
    )

    if direction == "sell":
        query = query.where(MarketListing.seller_id == user_id)
    elif direction == "buy":
        query = query.where(MarketListing.buyer_id == user_id)
    else:
        query = query.where(
            or_(MarketListing.seller_id == user_id, MarketListing.buyer_id == user_id)
        )

    if item_def_id is not None:
        query = query.where(MarketListing.item_def_id == item_def_id)

    if before_id is not None:
        query = query.where(MarketListing.id < before_id)

    query = query.order_by(MarketListing.id.desc()).limit(limit + 1)

    res = (await db.execute(query)).all()
    has_more = len(res) > limit
    page_rows = res[:limit]
    next_cursor = page_rows[-1][0].id if has_more and page_rows else None

    items: list[TradeHistoryItem] = []
    for listing, def_name in page_rows:
        is_sell = listing.seller_id == user_id
        item_direction: Literal["buy", "sell"] = "sell" if is_sell else "buy"
        if is_sell:
            fee = int(listing.fee or 0)
            net = int(listing.price - fee)
        else:
            fee = 0
            net = int(listing.price)

        items.append(
            TradeHistoryItem(
                id=listing.id,
                item_id=listing.item_id,
                item_def_id=listing.item_def_id,
                item_name=def_name,
                direction=item_direction,
                price=int(listing.price),
                fee=fee,
                net=net,
                created_at=listing.closed_at or listing.created_at,
            )
        )

    return TradeHistoryPageOut(
        items=items,
        next_cursor=next_cursor,
        summary=summary,
    )
