import math
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import AppError
from app.models import (
    Case,
    Collection,
    InventoryItem,
    ItemDef,
    ItemSet,
    ItemTransfer,
    MarketListing,
    User,
)
from app.schemas.market import (
    CaseMarketOut,
    DefMarketOut,
    DefSaleOut,
    ListingItemOut,
    ListingOut,
    MarketStatsOut,
)
from app.services.economy import apply_delta, lock_user
from app.services.items import (
    case_ref_out,
    check_trade_hold,
    check_transferable,
    item_def_out,
    items_out,
    lock_item_any,
    lock_items,
    unequip_items,
)
from app.services.notifications import notify
from app.services.settings import get_setting

_LISTING_NOT_FOUND = AppError(404, "LISTING_NOT_FOUND", "Лот не найден")
_LISTING_NOT_ACTIVE = AppError(400, "LISTING_NOT_ACTIVE", "Лот уже не активен")
_CANNOT_BUY_OWN = AppError(400, "CANNOT_BUY_OWN", "Нельзя купить свой лот")
_LISTING_LIMIT = AppError(400, "LISTING_LIMIT", "Достигнут лимит активных лотов")
_DEF_NOT_FOUND = AppError(404, "ITEM_DEF_NOT_FOUND", "Скин не найден")
_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")

_SORTS = ("price_asc", "price_desc", "new")


async def load_listing_def(db: AsyncSession, def_id: int) -> tuple[ItemDef, ItemSet, Collection | None]:
    row = (
        await db.execute(
            select(ItemDef, ItemSet, Collection)
            .join(ItemSet, ItemSet.id == ItemDef.set_id)
            .outerjoin(Collection, Collection.id == ItemDef.collection_id)
            .where(ItemDef.id == def_id)
        )
    ).first()
    if row is None or row[1].status == "draft":
        raise _DEF_NOT_FOUND
    return row[0], row[1], row[2]


async def create_listing(db: AsyncSession, user: User, item_id: int, price: int, now) -> MarketListing:
    # 1. Предмет владельца.
    items = await lock_items(db, user.id, [item_id])
    item = items[0]
    check_transferable(item)
    # 2. Trade hold.
    hold = int(await get_setting(db, "trade_hold_hours"))
    check_trade_hold(item, hold, now)
    # 3. Лимит активных лотов.
    active_count = await db.scalar(
        select(func.count())
        .select_from(MarketListing)
        .where(MarketListing.seller_id == user.id, MarketListing.status == "active")
    )
    max_listings = int(await get_setting(db, "market_max_listings"))
    if (active_count or 0) >= max_listings:
        raise _LISTING_LIMIT
    # 4. Снимаем со слота и переводим в listed.
    await unequip_items(db, [item.id])
    item.status = "listed"
    # 5. Лот.
    listing = MarketListing(
        item_id=item.id,
        item_def_id=item.item_def_id,
        case_id=item.case_id,
        seller_id=user.id,
        price=price,
        status="active",
        created_at=now,
    )
    db.add(listing)
    await db.flush()
    return listing


async def cancel_listing(
    db: AsyncSession,
    user: User,
    listing_id: int,
    now,
    *,
    by_admin: User | None = None,
) -> MarketListing:
    listing = await db.scalar(
        select(MarketListing)
        .where(MarketListing.id == listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if listing is None or (by_admin is None and listing.seller_id != user.id):
        raise _LISTING_NOT_FOUND
    if listing.status != "active":
        raise _LISTING_NOT_ACTIVE
    item = await lock_item_any(db, listing.item_id)
    item.status = "owned"
    listing.status = "cancelled"
    listing.closed_at = now
    await db.flush()
    return listing


async def buy_listing(db: AsyncSession, buyer: User, listing_id: int, now) -> MarketListing:
    listing = await db.scalar(
        select(MarketListing)
        .where(MarketListing.id == listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if listing is None:
        raise _LISTING_NOT_FOUND
    if listing.status != "active":
        raise _LISTING_NOT_ACTIVE
    if listing.seller_id == buyer.id:
        raise _CANNOT_BUY_OWN
    seller_id = listing.seller_id
    item = await lock_item_any(db, listing.item_id)
    # Пользователи — строго по возрастанию id (лоты → предметы уже заблокированы).
    for user_id in sorted({buyer.id, seller_id}):
        await lock_user(db, user_id)
    price = listing.price
    await apply_delta(db, buyer.id, -price, "market_buy", ref=str(listing.id))
    market_fee = await get_setting(db, "market_fee")
    fee = math.ceil(Decimal(price) * Decimal(str(market_fee)))
    seller_amount = price - fee
    if seller_amount > 0:
        await apply_delta(db, seller_id, seller_amount, "market_sale", ref=str(listing.id))
    item.user_id = buyer.id
    item.status = "owned"
    item.acquired_at = now
    listing.status = "sold"
    listing.buyer_id = buyer.id
    listing.fee = fee
    listing.closed_at = now
    listing.seller_seen = False
    db.add(
        ItemTransfer(
            item_id=item.id,
            from_user_id=seller_id,
            to_user_id=buyer.id,
            kind="market",
            ref=str(listing.id),
            seen=True,
        )
    )
    await db.flush()

    item_def = await db.get(ItemDef, listing.item_def_id)
    item_name = item_def.name if item_def is not None else f"#{listing.item_def_id}"
    await notify(
        db,
        user_id=seller_id,
        kind="market_sale",
        title="Продажа на маркете",
        body=f"Предмет {item_name} успешно продан. Выручка: {seller_amount} кристаллов",
        href=f"/market-item.html?def={listing.item_def_id}",
        now=now,
    )

    return listing


def _apply_filters(
    query,
    *,
    kind: str | None = None,
    set_code: str | None = None,
    collection: str | None = None,
    side: str | None = None,
    piece_type: str | None = None,
    rarity: str | None = None,
    def_id: int | None = None,
    case_id: int | None = None,
):
    base = (
        query.outerjoin(ItemDef, ItemDef.id == MarketListing.item_def_id)
        .outerjoin(Collection, Collection.id == ItemDef.collection_id)
        .outerjoin(ItemSet, ItemSet.id == ItemDef.set_id)
    )
    if kind == "case":
        base = base.where(MarketListing.case_id.is_not(None))
    elif kind in ("piece", "board"):
        base = base.where(ItemDef.kind == kind)
    if set_code is not None:
        base = base.where(ItemSet.code == set_code)
    if collection is not None:
        base = base.where(Collection.code == collection)
    if side is not None:
        base = base.where(ItemDef.side == side)
    if piece_type is not None:
        base = base.where(ItemDef.piece_type == piece_type)
    if rarity is not None:
        base = base.where(ItemDef.rarity == rarity)
    if def_id is not None:
        base = base.where(MarketListing.item_def_id == def_id)
    if case_id is not None:
        base = base.where(MarketListing.case_id == case_id)
    return base


def _order_for(sort: str):
    if sort == "price_asc":
        return MarketListing.price, MarketListing.id
    if sort == "price_desc":
        return MarketListing.price.desc(), MarketListing.id
    return MarketListing.created_at.desc(), MarketListing.id.desc()


async def _items_map(
    db: AsyncSession, listings: list[MarketListing]
) -> dict[int, InventoryItem]:
    item_ids = [listing.item_id for listing in listings]
    if not item_ids:
        return {}
    return {
        item.id: item
        for item in (
            await db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))
        ).all()
    }


async def _out_listings(
    db: AsyncSession,
    rows: list[tuple[MarketListing, str]],  # (listing, seller_login)
    viewer_id: int | None,
) -> list[ListingOut]:
    listings = [row[0] for row in rows]
    items_map = await _items_map(db, listings)
    # Порядок items_out сохраняет порядок входа: items в порядке listings.
    ordered_items: list[InventoryItem] = []
    for listing in listings:
        item = items_map.get(listing.item_id)
        if item is not None:
            ordered_items.append(item)
    outs = await items_out(db, ordered_items)
    paired: dict[int, ListingItemOut] = {}
    index = 0
    for listing, seller_login in rows:
        item_out = outs[index] if listing.item_id in items_map else None
        if item_out is not None:
            index += 1
            paired[listing.id] = ListingItemOut(
                id=item_out.id,
                kind=item_out.kind,
                item_def=item_out.item_def,
                case=item_out.case,
                wear=item_out.wear,
                exterior=item_out.exterior,
                image=item_out.image,
            )
    result = []
    for listing, seller_login in rows:
        result.append(
            ListingOut(
                id=listing.id,
                price=listing.price,
                status=listing.status,
                created_at=listing.created_at,
                closed_at=listing.closed_at,
                seller_login=seller_login,
                mine=viewer_id is not None and listing.seller_id == viewer_id,
                item=paired.get(listing.id),
            )
        )
    return result


async def browse(
    db: AsyncSession,
    viewer_id: int | None,
    *,
    kind: str | None = None,
    set_code: str | None = None,
    collection: str | None = None,
    side: str | None = None,
    piece_type: str | None = None,
    rarity: str | None = None,
    def_id: int | None = None,
    case_id: int | None = None,
    sort: str = "new",
    page: int = 1,
    limit: int = 20,
) -> tuple[list[ListingOut], int]:
    if sort not in _SORTS:
        raise AppError(422, "VALIDATION_ERROR", "Некорректная сортировка")
    filter_kwargs = dict(
        kind=kind,
        set_code=set_code,
        collection=collection,
        side=side,
        piece_type=piece_type,
        rarity=rarity,
        def_id=def_id,
        case_id=case_id,
    )
    filtered = _apply_filters(
        select(MarketListing, User.login).join(User, User.id == MarketListing.seller_id),
        **filter_kwargs,
    ).where(MarketListing.status == "active")

    count_query = _apply_filters(
        select(func.count()).select_from(MarketListing),
        **filter_kwargs,
    ).where(MarketListing.status == "active")
    total = await db.scalar(count_query) or 0

    rows = (
        await db.execute(
            filtered.order_by(*_order_for(sort)).offset((page - 1) * limit).limit(limit)
        )
    ).all()
    return await _out_listings(db, [tuple(row) for row in rows], viewer_id), total


async def def_market(db: AsyncSession, def_id: int, viewer_id: int | None) -> DefMarketOut:
    item_def, item_set, collection = await load_listing_def(db, def_id)
    active_rows = (
        await db.execute(
            select(MarketListing, User.login)
            .join(User, User.id == MarketListing.seller_id)
            .where(MarketListing.item_def_id == def_id, MarketListing.status == "active")
            .order_by(MarketListing.price, MarketListing.id)
            .limit(50)
        )
    ).all()
    listings = await _out_listings(db, [tuple(row) for row in active_rows], viewer_id)
    active_count = await db.scalar(
        select(func.count())
        .select_from(MarketListing)
        .where(MarketListing.item_def_id == def_id, MarketListing.status == "active")
    )
    min_price = await db.scalar(
        select(func.min(MarketListing.price)).where(
            MarketListing.item_def_id == def_id, MarketListing.status == "active"
        )
    )
    last_sale_price = await db.scalar(
        select(MarketListing.price)
        .where(MarketListing.item_def_id == def_id, MarketListing.status == "sold")
        .order_by(MarketListing.closed_at.desc(), MarketListing.id.desc())
        .limit(1)
    )
    sales_rows = (
        await db.scalars(
            select(MarketListing)
            .where(MarketListing.item_def_id == def_id, MarketListing.status == "sold")
            .order_by(MarketListing.closed_at.desc(), MarketListing.id.desc())
            .limit(50)
        )
    ).all()
    return DefMarketOut(
        item_def=item_def_out(item_def, item_set, collection),
        stats=MarketStatsOut(
            active_count=active_count or 0,
            min_price=min_price,
            last_sale_price=last_sale_price,
        ),
        listings=listings,
        sales=[
            DefSaleOut(price=listing.price, closed_at=listing.closed_at)
            for listing in sales_rows
        ],
    )


async def case_market(db: AsyncSession, case_id: int, viewer_id: int | None) -> CaseMarketOut:
    case = await db.get(Case, case_id)
    if case is None or case.status == "draft":
        raise _CASE_NOT_FOUND
    active_rows = (
        await db.execute(
            select(MarketListing, User.login)
            .join(User, User.id == MarketListing.seller_id)
            .where(MarketListing.case_id == case_id, MarketListing.status == "active")
            .order_by(MarketListing.price, MarketListing.id)
            .limit(50)
        )
    ).all()
    listings = await _out_listings(db, [tuple(row) for row in active_rows], viewer_id)
    active_count = await db.scalar(
        select(func.count())
        .select_from(MarketListing)
        .where(MarketListing.case_id == case_id, MarketListing.status == "active")
    )
    min_price = await db.scalar(
        select(func.min(MarketListing.price)).where(
            MarketListing.case_id == case_id, MarketListing.status == "active"
        )
    )
    last_sale_price = await db.scalar(
        select(MarketListing.price)
        .where(MarketListing.case_id == case_id, MarketListing.status == "sold")
        .order_by(MarketListing.closed_at.desc(), MarketListing.id.desc())
        .limit(1)
    )
    sales_rows = (
        await db.scalars(
            select(MarketListing)
            .where(MarketListing.case_id == case_id, MarketListing.status == "sold")
            .order_by(MarketListing.closed_at.desc(), MarketListing.id.desc())
            .limit(50)
        )
    ).all()
    return CaseMarketOut(
        case=case_ref_out(case),
        stats=MarketStatsOut(
            active_count=active_count or 0,
            min_price=min_price,
            last_sale_price=last_sale_price,
        ),
        listings=listings,
        sales=[
            DefSaleOut(price=listing.price, closed_at=listing.closed_at)
            for listing in sales_rows
        ],
    )


async def my_listings(
    db: AsyncSession, user: User, status: str | None
) -> list[ListingOut]:
    query = (
        select(MarketListing, User.login)
        .join(User, User.id == MarketListing.seller_id)
        .where(MarketListing.seller_id == user.id)
    )
    if status is not None:
        query = query.where(MarketListing.status == status)
    rows = (await db.execute(query.order_by(MarketListing.id.desc()))).all()
    return await _out_listings(db, [tuple(row) for row in rows], user.id)


async def take_unseen_sales(db: AsyncSession, user: User) -> list[dict]:
    """Проданные лоты продавца, о которых он ещё не знает; помечает их увиденными."""
    ids = list(
        await db.scalars(
            update(MarketListing)
            .where(
                MarketListing.seller_id == user.id,
                MarketListing.status == "sold",
                MarketListing.seller_seen.is_(False),
            )
            .values(seller_seen=True)
            .returning(MarketListing.id)
            .execution_options(synchronize_session=False)
        )
    )
    if not ids:
        return []
    buyer = aliased(User)
    rows = await db.execute(
        select(MarketListing, ItemDef.name, Case.name, buyer.login)
        .outerjoin(ItemDef, ItemDef.id == MarketListing.item_def_id)
        .outerjoin(Case, Case.id == MarketListing.case_id)
        .join(buyer, buyer.id == MarketListing.buyer_id)
        .where(MarketListing.id.in_(ids))
        .order_by(MarketListing.closed_at, MarketListing.id)
    )
    return [
        {
            "listing_id": listing.id,
            "name": def_name if def_name is not None else case_name,
            "price": listing.price,
            "payout": listing.price - (listing.fee or 0),
            "buyer_login": buyer_login,
            "closed_at": listing.closed_at,
        }
        for listing, def_name, case_name, buyer_login in rows
    ]
