from datetime import datetime

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
