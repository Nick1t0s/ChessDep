import app.core.clock as clock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import case as sql_case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import format_chance
from app.core.deps import current_user
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.db import get_db
from app.models import Case, CaseDrop, Collection, InventoryItem, ItemDef, Loadout, User
from app.schemas.items import (
    CaseDetailOut,
    CaseDropOut,
    CaseOpenOut,
    CaseOut,
    CollectionDetailOut,
    CollectionRef,
    ItemDefOut,
    ItemOut,
    LoadoutOut,
    LoadoutPutIn,
    PublicCollectionOut,
    RARITY_ORDER,
    Slot,
    UpgradeIn,
    UpgradeOut,
    UpgradePreviewOut,
)
from app.services import cases as cases_service
from app.services import upgrade as upgrade_service
from app.services.items import item_def_out, items_out, lock_items, slot_matches

router = APIRouter(prefix="/api/v1", tags=["items"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]

_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
_COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")
_ITEM_SLOT_MISMATCH = AppError(400, "ITEM_SLOT_MISMATCH", "Предмет не подходит в этот слот")

_ALL_SLOTS: tuple[str, ...] = ("P", "N", "B", "R", "Q", "K", "board")


@router.get("/collections", response_model=list[PublicCollectionOut])
async def list_collections(db: DbDep) -> list[PublicCollectionOut]:
    collections = (
        await db.scalars(
            select(Collection)
            .where(Collection.status.in_(("released", "retired")))
            .order_by(Collection.released_at.desc(), Collection.id)
        )
    ).all()
    counts = await db.execute(
        select(ItemDef.collection_id, func.count()).group_by(ItemDef.collection_id)
    )
    count_by = dict(counts.all())
    return [
        PublicCollectionOut(
            code=c.code,
            name=c.name,
            description=c.description,
            status=c.status,
            released_at=c.released_at,
            items_count=count_by.get(c.id, 0),
        )
        for c in collections
    ]


@router.get("/collections/{code}", response_model=CollectionDetailOut)
async def get_collection(code: str, db: DbDep) -> CollectionDetailOut:
    collection = await db.scalar(select(Collection).where(Collection.code == code))
    if collection is None or collection.status == "draft":
        raise _COLLECTION_NOT_FOUND
    defs = list(
        (await db.scalars(select(ItemDef).where(ItemDef.collection_id == collection.id))).all()
    )
    defs.sort(key=lambda d: (RARITY_ORDER[d.rarity], d.code))
    return CollectionDetailOut(
        code=collection.code,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        released_at=collection.released_at,
        items=[item_def_out(d, collection) for d in defs],
    )


@router.get("/item-defs", response_model=list[ItemDefOut])
async def list_item_defs(
    user: UserDep, db: DbDep, upgrade_target: bool = False
) -> list[ItemDefOut]:
    query = select(ItemDef, Collection).join(
        Collection, Collection.id == ItemDef.collection_id
    )
    if upgrade_target:
        query = query.where(Collection.status == "released", ItemDef.is_upgrade_target)
        query = query.order_by(ItemDef.value, ItemDef.id)
    else:
        query = query.where(Collection.status != "draft")
        query = query.order_by(ItemDef.id)
    rows = (await db.execute(query)).all()
    return [item_def_out(d, collection) for d, collection in rows]


@router.get("/inventory", response_model=list[ItemOut])
async def list_inventory(
    user: UserDep,
    db: DbDep,
    kind: Literal["piece_skin", "board_skin"] | None = None,
    slot: Slot | None = None,
    sort: Literal["rarity", "value", "new"] = "rarity",
) -> list[ItemOut]:
    query = (
        select(InventoryItem)
        .join(ItemDef, ItemDef.id == InventoryItem.item_def_id)
        .where(InventoryItem.user_id == user.id)
        .where(InventoryItem.status.in_(("owned", "listed")))
    )
    if kind is not None:
        query = query.where(ItemDef.kind == kind)
    if slot is not None:
        if slot == "board":
            query = query.where(ItemDef.kind == "board_skin")
        else:
            query = query.where(ItemDef.kind == "piece_skin", ItemDef.piece_type == slot)
    if sort == "rarity":
        rank = sql_case(
            *[
                (ItemDef.rarity == rarity, order)
                for rarity, order in RARITY_ORDER.items()
            ],
            else_=0,
        )
        query = query.order_by(rank.desc(), ItemDef.value.desc(), InventoryItem.id)
    elif sort == "value":
        query = query.order_by(ItemDef.value.desc(), InventoryItem.id)
    else:
        query = query.order_by(InventoryItem.acquired_at.desc(), InventoryItem.id.desc())
    items = (await db.scalars(query)).all()
    return list(await items_out(db, list(items)))


async def _loadout_out(db: AsyncSession, user: User) -> LoadoutOut:
    rows = await db.execute(
        select(Loadout, InventoryItem)
        .join(InventoryItem, InventoryItem.id == Loadout.inventory_item_id)
        .where(Loadout.user_id == user.id)
    )
    by_slot = {loadout.slot: item for loadout, item in rows}
    item_outs_by_id = {
        out.id: out
        for out in await items_out(db, [item for item in by_slot.values() if item is not None])
    }
    out: dict[str, ItemOut | None] = {}
    for slot_name in _ALL_SLOTS:
        item = by_slot.get(slot_name)
        out[slot_name] = item_outs_by_id[item.id] if item is not None else None
    return LoadoutOut(
        P=out["P"], N=out["N"], B=out["B"], R=out["R"], Q=out["Q"], K=out["K"], board=out["board"]
    )


@router.get("/loadout", response_model=LoadoutOut)
async def get_loadout(user: UserDep, db: DbDep) -> LoadoutOut:
    return await _loadout_out(db, user)


@router.put("/loadout/{slot}", response_model=LoadoutOut)
async def put_loadout(
    slot: Slot, body: LoadoutPutIn, user: UserDep, db: DbDep
) -> LoadoutOut:
    if body.inventory_item_id is None:
        row = await db.scalar(
            select(Loadout).where(Loadout.user_id == user.id, Loadout.slot == slot)
        )
        if row is not None:
            await db.delete(row)
    else:
        items = await lock_items(db, user.id, [body.inventory_item_id])
        item = items[0]
        item_def = await db.get(ItemDef, item.item_def_id)
        if not slot_matches(item_def, slot):
            raise _ITEM_SLOT_MISMATCH
        # Upsert вместо «select, затем insert или update» — иначе два
        # параллельных PUT создают дубликат (user_id, slot) или теряют строку.
        await db.execute(
            insert(Loadout)
            .values(user_id=user.id, slot=slot, inventory_item_id=item.id)
            .on_conflict_do_update(
                index_elements=["user_id", "slot"],
                set_={"inventory_item_id": item.id},
            )
        )
    await db.flush()
    return await _loadout_out(db, user)


@router.get("/cases", response_model=list[CaseOut])
async def list_cases(db: DbDep) -> list[CaseOut]:
    rows = (
        await db.execute(
            select(Case, Collection)
            .join(Collection, Collection.id == Case.collection_id)
            .where(Collection.status == "released", Case.is_active)
            .order_by(Case.sort, Case.id)
        )
    ).all()
    return [
        CaseOut(
            id=case.id,
            code=case.code,
            name=case.name,
            price=case.price,
            collection=CollectionRef(code=collection.code, name=collection.name),
        )
        for case, collection in rows
    ]


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
async def get_case(case_id: int, db: DbDep) -> CaseDetailOut:
    try:
        case, collection, drops = await cases_service.openable_case(db, case_id)
    except AppError as exc:
        if exc.code == "CASE_NOT_AVAILABLE":
            # Неоткрываемый (retired/неактивный/без дропов) — 404.
            raise _CASE_NOT_FOUND
        raise
    defs = {
        d.id: d
        for d in (
            await db.scalars(select(ItemDef).where(ItemDef.collection_id == collection.id))
        ).all()
    }
    total = sum(d.weight for d in drops)
    return CaseDetailOut(
        id=case.id,
        code=case.code,
        name=case.name,
        price=case.price,
        collection=CollectionRef(code=collection.code, name=collection.name),
        drops=[
            CaseDropOut(
                item_def=item_def_out(defs[drop.item_def_id], collection),
                weight=drop.weight,
                chance=drop.weight / total,
                chance_text=format_chance(drop.weight / total),
            )
            for drop in drops
        ],
    )


@router.post("/cases/{case_id}/open", response_model=CaseOpenOut)
async def open_case(case_id: int, user: UserDep, db: DbDep) -> CaseOpenOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await cases_service.open_case(db, user, case_id, clock.now())


@router.post("/upgrade/preview", response_model=UpgradePreviewOut)
async def preview(body: UpgradeIn, user: UserDep, db: DbDep) -> UpgradePreviewOut:
    return await upgrade_service.preview(db, user, body.input_ids, body.target_def_id)


@router.post("/upgrade", response_model=UpgradeOut)
async def run_upgrade(body: UpgradeIn, user: UserDep, db: DbDep) -> UpgradeOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await upgrade_service.execute(db, user, body.input_ids, body.target_def_id, clock.now())
