from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Collection, InventoryItem, ItemDef, Loadout
from app.schemas.items import CollectionRef, ItemDefOut, ItemOut, exterior
from app.services.rolls import get_rng

_ITEM_NOT_OWNED = AppError(400, "ITEM_NOT_OWNED", "Предмет недоступен")


def item_def_out(d: ItemDef, collection: Collection) -> ItemDefOut:
    return ItemDefOut(
        id=d.id,
        code=d.code,
        name=d.name,
        kind=d.kind,
        piece_type=d.piece_type,
        rarity=d.rarity,
        value=d.value,
        asset=d.asset,
        collection=CollectionRef(code=collection.code, name=collection.name),
    )


async def item_out(db: AsyncSession, item: InventoryItem) -> ItemOut:
    d = await db.get(ItemDef, item.item_def_id)
    collection = await db.get(Collection, d.collection_id)
    slot = await db.scalar(select(Loadout.slot).where(Loadout.inventory_item_id == item.id))
    wear = float(item.wear)
    return ItemOut(
        id=item.id,
        item_def=item_def_out(d, collection),
        wear=wear,
        exterior=exterior(wear),
        status=item.status,
        equipped_slot=slot,
        source=item.source,
        acquired_at=item.acquired_at,
    )


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
    """Пакетная версия item_out: ровно 3 запроса на любой размер списка.

    def'ы (IN), коллекции (IN), слоты loadouts (IN); порядок сохраняется.
    """
    if not items:
        return []
    def_ids = {item.item_def_id for item in items}
    defs = {
        d.id: d
        for d in (await db.scalars(select(ItemDef).where(ItemDef.id.in_(def_ids)))).all()
    }
    collection_ids = {d.collection_id for d in defs.values()}
    collections: dict[int, Collection] = {}
    if collection_ids:
        collections = {
            c.id: c
            for c in (
                await db.scalars(select(Collection).where(Collection.id.in_(collection_ids)))
            ).all()
        }
    item_ids = [item.id for item in items]
    slots = {
        row[0]: row[1]
        for row in (
            await db.execute(select(Loadout.inventory_item_id, Loadout.slot).where(
                Loadout.inventory_item_id.in_(item_ids)
            ))
        ).all()
    }
    result: list[ItemOut] = []
    for item in items:
        d = defs[item.item_def_id]
        collection = collections[d.collection_id]
        wear = float(item.wear)
        result.append(
            ItemOut(
                id=item.id,
                item_def=item_def_out(d, collection),
                wear=wear,
                exterior=exterior(wear),
                status=item.status,
                equipped_slot=slots.get(item.id),
                source=item.source,
                acquired_at=item.acquired_at,
            )
        )
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


async def loadout_snapshot(db: AsyncSession, user_id: int) -> dict[str, dict]:
    rows = await db.execute(
        select(Loadout, ItemDef)
        .join(InventoryItem, InventoryItem.id == Loadout.inventory_item_id)
        .join(ItemDef, ItemDef.id == InventoryItem.item_def_id)
        .where(Loadout.user_id == user_id)
    )
    snapshot: dict[str, dict] = {}
    for loadout, item_def in rows:
        snapshot[loadout.slot] = {
            "code": item_def.code,
            "name": item_def.name,
            "rarity": item_def.rarity,
            "asset": item_def.asset,
        }
    return snapshot


def slot_matches(item_def: ItemDef, slot: str) -> bool:
    if slot == "board":
        return item_def.kind == "board_skin"
    return item_def.kind == "piece_skin" and item_def.piece_type == slot
