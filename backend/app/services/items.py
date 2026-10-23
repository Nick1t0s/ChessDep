from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Case, Collection, InventoryItem, ItemDef, ItemSet, Loadout
from app.schemas.items import (
    CaseRefOut,
    CollectionRef,
    ItemDefOut,
    ItemOut,
    SetRef,
    exterior,
)
from app.seed_data import BASE_DEF_IDS, LOADOUT_SLOTS
from app.services.rolls import get_rng

_ITEM_NOT_OWNED = AppError(400, "ITEM_NOT_OWNED", "Предмет недоступен")

ITEM_BOUND = AppError(400, "ITEM_BOUND", "Базовый предмет нельзя передать или апгрейдить")
ITEM_NOT_UPGRADABLE = AppError(400, "ITEM_NOT_UPGRADABLE", "Кейс нельзя апгрейдить")
LOADOUT_INCOMPLETE = AppError(400, "LOADOUT_INCOMPLETE", "Экипируйте скины на все фигуры и доску")


def item_def_out(d: ItemDef, item_set: ItemSet, collection: Collection | None) -> ItemDefOut:
    return ItemDefOut(
        id=d.id,
        code=d.code,
        name=d.name,
        kind=d.kind,
        side=d.side,
        piece_type=d.piece_type,
        rarity=d.rarity,
        value=d.value,
        asset=d.asset,
        set=SetRef(code=item_set.code, name=item_set.name),
        collection=None if collection is None else CollectionRef(code=collection.code, name=collection.name),
    )


def case_ref_out(case: Case) -> CaseRefOut:
    return CaseRefOut(
        id=case.id,
        code=case.code,
        name=case.name,
        kind=case.kind,
        price=case.price,
    )


async def defs_out(db: AsyncSession, def_ids: Iterable[int]) -> dict[int, ItemDefOut]:
    """Пакетная сборка ItemDefOut: ровно ≤ 3 запроса (defs, sets, collections)."""
    ids = list(set(def_ids))
    if not ids:
        return {}
    defs = {
        d.id: d
        for d in (await db.scalars(select(ItemDef).where(ItemDef.id.in_(ids)))).all()
    }
    set_ids = {d.set_id for d in defs.values()}
    sets: dict[int, ItemSet] = {}
    if set_ids:
        sets = {
            s.id: s
            for s in (await db.scalars(select(ItemSet).where(ItemSet.id.in_(set_ids)))).all()
        }
    collection_ids = {d.collection_id for d in defs.values()} - {None}
    collections: dict[int, Collection] = {}
    if collection_ids:
        collections = {
            c.id: c
            for c in (
                await db.scalars(select(Collection).where(Collection.id.in_(collection_ids)))
            ).all()
        }
    return {
        d.id: item_def_out(d, sets[d.set_id], None if d.collection_id is None else collections[d.collection_id])
        for d in defs.values()
    }


def _skin_out(item: InventoryItem, d: ItemDefOut, equipped_slot: str | None) -> ItemOut:
    wear = float(item.wear) if item.wear is not None else 0.0
    return ItemOut(
        id=item.id,
        kind="skin",
        item_def=d,
        case=None,
        wear=wear,
        exterior=exterior(wear),
        status=item.status,
        equipped_slot=equipped_slot,
        source=item.source,
        bound=item.source == "base",
        acquired_at=item.acquired_at,
    )


def _case_item_out(
    item: InventoryItem, case: Case, equipped_slot: str | None
) -> ItemOut:
    return ItemOut(
        id=item.id,
        kind="case",
        item_def=None,
        case=case_ref_out(case),
        wear=None,
        exterior=None,
        status=item.status,
        equipped_slot=equipped_slot,
        source=item.source,
        bound=item.source == "base",
        acquired_at=item.acquired_at,
    )


async def item_out(db: AsyncSession, item: InventoryItem) -> ItemOut:
    return (await items_out(db, [item]))[0]


async def create_item(
    db: AsyncSession,
    *,
    user_id: int,
    def_id: int,
    source: str,
    source_ref: str | None,
    now: datetime,
) -> InventoryItem:
    item = InventoryItem(
        user_id=user_id,
        item_def_id=def_id,
        wear=get_rng().random(),
        status="owned",
        source=source,
        source_ref=source_ref,
        created_at=now,
        acquired_at=now,
    )
    db.add(item)
    await db.flush()
    return item


async def create_case_item(
    db: AsyncSession,
    *,
    user_id: int,
    case_id: int,
    source: str,
    source_ref: str | None,
    now: datetime,
) -> InventoryItem:
    item = InventoryItem(
        user_id=user_id,
        case_id=case_id,
        wear=None,
        status="owned",
        source=source,
        source_ref=source_ref,
        created_at=now,
        acquired_at=now,
    )
    db.add(item)
    await db.flush()
    return item


async def grant_base_items(db: AsyncSession, user_id: int, now: datetime) -> None:
    """13 базовых предметов + экипировка во все 13 слотов (без RNG)."""
    slot_by_item: list[tuple[str, InventoryItem]] = []
    for def_id, slot in zip(BASE_DEF_IDS, LOADOUT_SLOTS):
        item = InventoryItem(
            user_id=user_id,
            item_def_id=def_id,
            wear=0.0,
            status="owned",
            source="base",
            source_ref=None,
            created_at=now,
            acquired_at=now,
        )
        db.add(item)
        slot_by_item.append((slot, item))
    await db.flush()
    for slot, item in slot_by_item:
        db.add(Loadout(user_id=user_id, slot=slot, inventory_item_id=item.id))
    await db.flush()


def check_transferable(item: InventoryItem) -> None:
    if item.source == "base":
        raise ITEM_BOUND


async def loadout_complete(db: AsyncSession, user_id: int) -> bool:
    count = await db.scalar(
        select(func.count()).select_from(Loadout).where(Loadout.user_id == user_id)
    )
    return count == 13


async def ensure_loadout_complete(db: AsyncSession, user_id: int) -> None:
    if not await loadout_complete(db, user_id):
        raise LOADOUT_INCOMPLETE


async def loadout_snapshot(db: AsyncSession, user_id: int, side: str) -> dict[str, dict]:
    """Слоты одной стороны (side = 'w'|'b') без префикса + 'board'."""
    rows = await db.execute(
        select(Loadout, ItemDef)
        .join(InventoryItem, InventoryItem.id == Loadout.inventory_item_id)
        .join(ItemDef, ItemDef.id == InventoryItem.item_def_id)
        .where(Loadout.user_id == user_id, Loadout.slot.startswith(side) | (Loadout.slot == "board"))
    )
    snapshot: dict[str, dict] = {}
    for loadout, item_def in rows:
        snapshot["board" if loadout.slot == "board" else loadout.slot[1:]] = {
            "code": item_def.code,
            "name": item_def.name,
            "rarity": item_def.rarity,
            "asset": item_def.asset,
        }
    return snapshot


def slot_matches(item_def: ItemDef | None, slot: str) -> bool:
    if item_def is None:
        return False
    if item_def.kind == "board":
        return slot == "board"
    return slot == item_def.side + item_def.piece_type


async def _fetch_owned_items(
    db: AsyncSession, user_id: int, ids: list[int], *, for_update: bool
) -> list[InventoryItem]:
    unique_ids = sorted(set(ids))
    query = (
        select(InventoryItem)
        .where(InventoryItem.id.in_(unique_ids), InventoryItem.user_id == user_id)
        .order_by(InventoryItem.id)
    )
    if for_update:
        # FOR UPDATE только с populate_existing=True.
        query = query.with_for_update().execution_options(populate_existing=True)
    items = list((await db.scalars(query)).all())
    if len(items) != len(unique_ids):
        raise _ITEM_NOT_OWNED
    if any(item.status != "owned" for item in items):
        raise _ITEM_NOT_OWNED
    return items


async def lock_items(db: AsyncSession, user_id: int, ids: list[int]) -> list[InventoryItem]:
    return await _fetch_owned_items(db, user_id, ids, for_update=True)


async def lock_item_any(db: AsyncSession, item_id: int) -> InventoryItem | None:
    """FOR UPDATE + populate_existing, без проверки владельца и статуса."""
    return await db.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def items_out(db: AsyncSession, items: list[InventoryItem]) -> list[ItemOut]:
    """Пакетная сборка ItemOut для скинов и кейсов; порядок сохраняется."""
    if not items:
        return []
    item_ids = [item.id for item in items]
    slots = {
        row[0]: row[1]
        for row in (
            await db.execute(
                select(Loadout.inventory_item_id, Loadout.slot).where(
                    Loadout.inventory_item_id.in_(item_ids)
                )
            )
        ).all()
    }
    def_ids = {i for i in (item.item_def_id for item in items) if i is not None}
    defs: dict[int, ItemDefOut] = await defs_out(db, def_ids)
    case_ids = {item.case_id for item in items} - {None}
    cases: dict[int, Case] = {}
    if case_ids:
        cases = {
            c.id: c
            for c in (
                await db.scalars(select(Case).where(Case.id.in_(case_ids)))
            ).all()
        }
    result: list[ItemOut] = []
    for item in items:
        equipped_slot = slots.get(item.id)
        if item.case_id is not None:
            result.append(_case_item_out(item, cases[item.case_id], equipped_slot))
        else:
            assert item.item_def_id is not None
            result.append(_skin_out(item, defs[item.item_def_id], equipped_slot))
    return result


def check_trade_hold(item: InventoryItem, hold_hours: int, now: datetime) -> None:
    if hold_hours > 0 and now < item.acquired_at + timedelta(hours=hold_hours):
        limit = (item.acquired_at + timedelta(hours=hold_hours)).isoformat()
        raise AppError(400, "TRADE_HOLD", f"Предмет можно передать после {limit}")


async def load_items(db: AsyncSession, user_id: int, ids: list[int]) -> list[InventoryItem]:
    """Тот же запрос, что lock_items, но без FOR UPDATE (для preview)."""
    return await _fetch_owned_items(db, user_id, ids, for_update=False)


async def unequip_items(db: AsyncSession, item_ids: list[int]) -> None:
    if item_ids:
        await db.execute(delete(Loadout).where(Loadout.inventory_item_id.in_(item_ids)))
