from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Case, CaseDrop, Collection, ItemDef, User
from app.schemas.items import CaseOpenOut, ItemDefOut
from app.services.economy import apply_delta
from app.services.items import create_item, item_def_out, item_out
from app.services.rolls import get_rng, record_roll

_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
_CASE_NOT_AVAILABLE = AppError(400, "CASE_NOT_AVAILABLE", "Кейс недоступен")

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


async def openable_case(
    db: AsyncSession, case_id: int
) -> tuple[Case, Collection, list[CaseDrop]]:
    case = await db.get(Case, case_id)
    if case is None:
        raise _CASE_NOT_FOUND
    collection_ref = await db.get(Collection, case.collection_id)
    if collection_ref is None or collection_ref.status == "draft":
        # Черновики публично не существуют.
        raise _CASE_NOT_FOUND
    if collection_ref.status == "retired" or not case.is_active:
        raise _CASE_NOT_AVAILABLE
    drops = list(
        (
            await db.scalars(
                select(CaseDrop)
                .where(CaseDrop.case_id == case_id)
                .order_by(CaseDrop.item_def_id)
            )
        ).all()
    )
    if not drops:
        raise _CASE_NOT_AVAILABLE
    return case, collection_ref, drops


async def open_case(db: AsyncSession, user: User, case_id: int, now: datetime) -> CaseOpenOut:
    case, collection_ref, drops = await openable_case(db, case_id)
    # 2. Списание (порядок блокировок: пользователь последний и единственный).
    balance = await apply_delta(db, user.id, -case.price, "case_purchase", ref=str(case.id))
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
    # 6. create_item расходует следующий rng.random() на wear.
    item = await create_item(
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
        input={"case_id": case.id, "price": case.price},
        outcome={"item_def_id": winner.item_def_id, "item_id": item.id},
    )
    # 8. defs — все def, встречающиеся в ленте.
    defs: dict[str, ItemDefOut] = {}
    for def_id in strip:
        key = str(def_id)
        if key in defs:
            continue
        d = await db.get(ItemDef, def_id)
        defs[key] = item_def_out(d, collection_ref)
    return CaseOpenOut(
        item=await item_out(db, item),
        strip=strip,
        win_index=win_index,
        defs=defs,
        balance=balance,
    )
