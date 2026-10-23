from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import format_chance
from app.core.errors import AppError
from app.models import Case, CaseDrop, Collection, ItemDef, ItemSet, User
from app.schemas.items import (
    CaseBuyOut,
    CaseDetailOut,
    CaseDropOut,
    CaseOpenOut,
    CollectionRef,
    ItemDefOut,
    SetRef,
    ShopCaseOut,
)
from app.services.economy import apply_delta
from app.services.items import create_case_item, create_item, defs_out, item_out, lock_items
from app.services.rolls import get_rng, record_roll

_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
_CASE_NOT_AVAILABLE = AppError(400, "CASE_NOT_AVAILABLE", "Кейс сейчас не продаётся")

STRIP_LENGTH = 60
WIN_INDEX_MIN = 45
WIN_INDEX_RANGE = 10


def auto_weights(
    item_defs: list[ItemDef], rarity_weights: dict[str, int]
) -> dict[int, int]:
    """Вес каждого скина = rarity_weights[r] * 1000 // n (n — число скинов редкости r)."""
    by_rarity: dict[str, int] = {}
    for d in item_defs:
        by_rarity[d.rarity] = by_rarity.get(d.rarity, 0) + 1
    share: dict[str, int] = {}
    for rarity, count in by_rarity.items():
        base = int(rarity_weights.get(rarity, 0))
        weight = base * 1000 // count
        if weight > 0:
            share[rarity] = weight
    weights: dict[int, int] = {}
    for d in item_defs:
        if d.rarity in share:
            weights[d.id] = share[d.rarity]
    return weights


def weighted_pick(drops: list[CaseDrop], r: float) -> CaseDrop:
    """drops отсортированы по item_def_id; первый drop с накопленной суммой > target."""
    total = sum(d.weight for d in drops)
    target = r * total
    cumulative = 0
    for drop in drops:
        cumulative += drop.weight
        if cumulative > target:
            return drop
    return drops[-1]


def on_sale_now(case: Case, now: datetime) -> bool:
    return (
        case.status == "on_sale"
        and (case.sale_starts_at is None or now >= case.sale_starts_at)
        and (case.sale_ends_at is None or now < case.sale_ends_at)
        and (case.stock_limit is None or case.sold_count < case.stock_limit)
    )


async def shop_case_outs(db: AsyncSession, cases_list: list[Case]) -> list[ShopCaseOut]:
    if not cases_list:
        return []
    set_ids = {c.set_id for c in cases_list if c.set_id is not None}
    collection_ids = {c.collection_id for c in cases_list if c.collection_id is not None}
    sets: dict[int, ItemSet] = {}
    if set_ids:
        sets = {
            s.id: s
            for s in (await db.scalars(select(ItemSet).where(ItemSet.id.in_(set_ids)))).all()
        }
    collections: dict[int, Collection] = {}
    if collection_ids:
        collections = {
            c.id: c
            for c in (await db.scalars(select(Collection).where(Collection.id.in_(collection_ids)))).all()
        }
    result: list[ShopCaseOut] = []
    for case in cases_list:
        case_set = sets.get(case.set_id)
        collection = collections.get(case.collection_id)
        result.append(
            ShopCaseOut(
                id=case.id,
                code=case.code,
                name=case.name,
                kind=case.kind,
                set=(
                    SetRef(code=case_set.code, name=case_set.name)
                    if case_set is not None
                    else None
                ),
                collection=(
                    CollectionRef(code=collection.code, name=collection.name)
                    if collection is not None
                    else None
                ),
                price=case.price,
                stock_limit=case.stock_limit,
                stock_left=(
                    None if case.stock_limit is None else case.stock_limit - case.sold_count
                ),
                sale_starts_at=case.sale_starts_at,
                sale_ends_at=case.sale_ends_at,
            )
        )
    return result


async def case_detail(db: AsyncSession, case_id: int, now: datetime) -> CaseDetailOut:
    case = await db.get(Case, case_id)
    if case is None or case.status == "draft":
        raise _CASE_NOT_FOUND
    drops = list(
        (
            await db.scalars(
                select(CaseDrop)
                .where(CaseDrop.case_id == case_id)
                .order_by(CaseDrop.item_def_id)
            )
        ).all()
    )
    total = sum(d.weight for d in drops)
    defs = await defs_out(db, [d.item_def_id for d in drops])
    drop_outs = [
        CaseDropOut(
            item_def=defs[d.item_def_id],
            weight=d.weight,
            chance=d.weight / total,
            chance_text=format_chance(d.weight / total),
        )
        for d in drops
    ]
    base = (await shop_case_outs(db, [case]))[0]
    return CaseDetailOut(
        **base.model_dump(),
        on_sale_now=on_sale_now(case, now),
        drops=drop_outs,
    )


async def buy_case(db: AsyncSession, user: User, case_id: int, now: datetime) -> CaseBuyOut:
    case = await db.get(Case, case_id)
    if case is None or case.status == "draft":
        raise _CASE_NOT_FOUND
    if not on_sale_now(case, now):
        raise _CASE_NOT_AVAILABLE
    row = (
        await db.execute(
            update(Case)
            .where(
                Case.id == case_id,
                Case.status == "on_sale",
                or_(Case.stock_limit.is_(None), Case.sold_count < Case.stock_limit),
            )
            .values(sold_count=Case.sold_count + 1)
            .returning(Case.sold_count, Case.stock_limit)
        )
    ).one_or_none()
    if row is None:
        raise _CASE_NOT_AVAILABLE
    sold_count, stock_limit = row
    if stock_limit is not None and sold_count >= stock_limit:
        await db.execute(update(Case).where(Case.id == case_id).values(status="off_sale"))
    balance = await apply_delta(db, user.id, -case.price, "case_purchase", ref=str(case.id))
    item = await create_case_item(
        db,
        user_id=user.id,
        case_id=case.id,
        source="shop",
        source_ref=str(case.id),
        now=now,
    )
    return CaseBuyOut(item=await item_out(db, item), balance=balance)


async def open_case_item(db: AsyncSession, user: User, item_id: int, now: datetime) -> CaseOpenOut:
    items = await lock_items(db, user.id, [item_id])
    item = items[0]
    if item.case_id is None:
        raise AppError(400, "ITEM_NOT_CASE", "Это не кейс")
    case = await db.get(Case, item.case_id)
    drops = list(
        (
            await db.scalars(
                select(CaseDrop)
                .where(CaseDrop.case_id == case.id)
                .order_by(CaseDrop.item_def_id)
            )
        ).all()
    )
    if not drops:
        raise _CASE_NOT_AVAILABLE
    item.status = "burned"
    item.burned_at = now
    # Порядок вызовов rng.random() фиксирован, на нём держатся тесты.
    rng = get_rng()
    r_win = rng.random()
    winner = weighted_pick(drops, r_win)
    win_index = WIN_INDEX_MIN + int(rng.random() * WIN_INDEX_RANGE)
    strip: list[int] = []
    for i in range(STRIP_LENGTH):
        if i == win_index:
            strip.append(winner.item_def_id)
        else:
            strip.append(weighted_pick(drops, rng.random()).item_def_id)
    # create_item расходует следующий rng.random() на wear.
    new_item = await create_item(
        db,
        user_id=user.id,
        def_id=winner.item_def_id,
        source="case",
        source_ref=str(case.id),
        now=now,
    )
    total = sum(d.weight for d in drops)
    await record_roll(
        db,
        user_id=user.id,
        kind="case_open",
        ref=str(case.id),
        chance=winner.weight / total,
        roll_value=r_win,
        input={"case_id": case.id, "inventory_item_id": item.id},
        outcome={"item_def_id": winner.item_def_id, "item_id": new_item.id},
    )
    # defs — все def, встречающиеся в ленте.
    defs = await defs_out(db, set(strip))
    return CaseOpenOut(
        item=await item_out(db, new_item),
        strip=strip,
        win_index=win_index,
        defs={str(def_id): out for def_id, out in defs.items()},
    )
