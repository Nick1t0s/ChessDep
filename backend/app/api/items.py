import app.core.clock as clock
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import case as sql_case, func, nulls_last, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.db import get_db
from app.models import (
    Case,
    Collection,
    InventoryItem,
    ItemDef,
    ItemSet,
    Loadout,
    User,
)
from app.seed_data import CANONICAL_SLOTS, LOADOUT_SLOTS
from app.schemas.items import (
    CaseBuyOut,
    CaseDetailOut,
    CaseOpenOut,
    CollectionDetailOut,
    ItemDefOut,
    ItemOut,
    LoadoutOut,
    LoadoutPutIn,
    PublicSetOut,
    RARITY_ORDER,
    SetCollectionOut,
    SetDetailOut,
    SetRef,
    ShopCaseOut,
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

_SET_NOT_FOUND = AppError(404, "SET_NOT_FOUND", "Набор не найден")
_COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")
_ITEM_SLOT_MISMATCH = AppError(400, "ITEM_SLOT_MISMATCH", "Предмет не подходит в этот слот")


@router.get("/sets", response_model=list[PublicSetOut])
async def list_sets(db: DbDep) -> list[PublicSetOut]:
    sets = list(
        (
            await db.scalars(
                select(ItemSet)
                .where(
                    ItemSet.status.in_(("released", "retired")),
                    ItemSet.is_base.is_(False),
                )
                .order_by(ItemSet.released_at.desc(), ItemSet.id)
            )
        ).all()
    )
    collection_counts: dict[int, int] = {}
    if sets:
        rows = await db.execute(
            select(Collection.set_id, func.count())
            .where(Collection.set_id.in_([s.id for s in sets]))
            .group_by(Collection.set_id)
        )
        collection_counts = dict(rows.all())
    board_counts: dict[int, int] = {}
    if sets:
        rows = await db.execute(
            select(ItemDef.set_id, func.count())
            .where(ItemDef.set_id.in_([s.id for s in sets]), ItemDef.kind == "board")
            .group_by(ItemDef.set_id)
        )
        board_counts = dict(rows.all())
    return [
        PublicSetOut(
            code=s.code,
            name=s.name,
            description=s.description,
            status=s.status,
            released_at=s.released_at,
            collections_count=collection_counts.get(s.id, 0),
            boards_count=board_counts.get(s.id, 0),
        )
        for s in sets
    ]


@router.get("/sets/{code}", response_model=SetDetailOut)
async def get_set(code: str, db: DbDep) -> SetDetailOut:
    set_ = await db.scalar(select(ItemSet).where(ItemSet.code == code))
    if set_ is None or set_.status == "draft":
        raise _SET_NOT_FOUND
    collections = list(
        (
            await db.scalars(
                select(Collection)
                .where(Collection.set_id == set_.id)
                .order_by(Collection.id)
            )
        ).all()
    )
    defs_by_collection: dict[int, list[ItemDef]] = {}
    if collections:
        defs = list(
            (
                await db.scalars(
                    select(ItemDef).where(
                        ItemDef.collection_id.in_([c.id for c in collections])
                    )
                )
            ).all()
        )
        for d in defs:
            # kind = piece ⇒ side/piece_type гарантированно заданы (ck_item_defs_kind_shape).
            defs_by_collection.setdefault(d.collection_id, []).append(d)
    for defs in defs_by_collection.values():
        defs.sort(key=lambda d: CANONICAL_SLOTS.index(d.side + d.piece_type))
    boards = list(
        (
            await db.scalars(
                select(ItemDef)
                .where(ItemDef.set_id == set_.id, ItemDef.kind == "board")
                .order_by(ItemDef.id)
            )
        ).all()
    )
    return SetDetailOut(
        code=set_.code,
        name=set_.name,
        description=set_.description,
        status=set_.status,
        released_at=set_.released_at,
        collections=[
            SetCollectionOut(
                code=c.code,
                name=c.name,
                description=c.description,
                items=[
                    item_def_out(d, set_, c)
                    for d in defs_by_collection.get(c.id, [])
                ],
            )
            for c in collections
        ],
        boards=[item_def_out(d, set_, None) for d in boards],
    )


@router.get("/collections/{code}", response_model=CollectionDetailOut)
async def get_collection(code: str, db: DbDep) -> CollectionDetailOut:
    row = (
        await db.execute(
            select(Collection, ItemSet)
            .join(ItemSet, ItemSet.id == Collection.set_id)
            .where(Collection.code == code)
        )
    ).first()
    if row is None or row[1].status == "draft":
        raise _COLLECTION_NOT_FOUND
    collection, set_ = row
    defs = list(
        (
            await db.scalars(select(ItemDef).where(ItemDef.collection_id == collection.id))
        ).all()
    )
    defs.sort(key=lambda d: CANONICAL_SLOTS.index(d.side + d.piece_type))
    return CollectionDetailOut(
        code=collection.code,
        name=collection.name,
        description=collection.description,
        set=SetRef(code=set_.code, name=set_.name),
        items=[item_def_out(d, set_, collection) for d in defs],
    )


@router.get("/item-defs", response_model=list[ItemDefOut])
async def list_item_defs(
    user: UserDep, db: DbDep, upgrade_target: bool = False
) -> list[ItemDefOut]:
    query = (
        select(ItemDef, ItemSet, Collection)
        .join(ItemSet, ItemSet.id == ItemDef.set_id)
        .outerjoin(Collection, Collection.id == ItemDef.collection_id)
        .where(ItemSet.is_base.is_(False))
    )
    if upgrade_target:
        query = query.where(
            ItemSet.status == "released", ItemDef.is_upgrade_target
        )
        query = query.order_by(ItemDef.value, ItemDef.id)
    else:
        query = query.where(ItemSet.status != "draft")
        query = query.order_by(ItemDef.id)
    rows = (await db.execute(query)).all()
    return [item_def_out(d, set_, collection) for d, set_, collection in rows]


@router.get("/shop", response_model=list[ShopCaseOut])
async def get_shop(db: DbDep) -> list[ShopCaseOut]:
    cases = list(
        (
            await db.scalars(
                select(Case).where(Case.status == "on_sale").order_by(Case.sort, Case.id)
            )
        ).all()
    )
    now = clock.now()
    return await cases_service.shop_case_outs(
        db, [case for case in cases if cases_service.on_sale_now(case, now)]
    )


@router.get("/cases/{case_id}", response_model=CaseDetailOut)
async def get_case(case_id: int, db: DbDep) -> CaseDetailOut:
    return await cases_service.case_detail(db, case_id, clock.now())


@router.post("/cases/{case_id}/buy", response_model=CaseBuyOut)
async def buy_case(case_id: int, user: UserDep, db: DbDep) -> CaseBuyOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await cases_service.buy_case(db, user, case_id, clock.now())


@router.post("/inventory/{item_id}/open", response_model=CaseOpenOut)
async def open_case_item(item_id: int, user: UserDep, db: DbDep) -> CaseOpenOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await cases_service.open_case_item(db, user, item_id, clock.now())


@router.get("/inventory", response_model=list[ItemOut])
async def list_inventory(
    user: UserDep,
    db: DbDep,
    kind: Literal["piece", "board", "case"] | None = None,
    side: Literal["w", "b"] | None = None,
    slot: Slot | None = None,
    sort: Literal["rarity", "value", "new"] = "rarity",
) -> list[ItemOut]:
    query = (
        select(InventoryItem)
        .outerjoin(ItemDef, ItemDef.id == InventoryItem.item_def_id)
        .where(InventoryItem.user_id == user.id)
        .where(InventoryItem.status.in_(("owned", "listed")))
    )
    if kind == "case":
        query = query.where(InventoryItem.case_id.is_not(None))
    elif kind is not None:
        query = query.where(ItemDef.kind == kind)
    if side is not None:
        query = query.where(ItemDef.side == side)
    if slot is not None:
        if slot == "board":
            query = query.where(ItemDef.kind == "board")
        else:
            query = query.where(ItemDef.side == slot[0], ItemDef.piece_type == slot[1])
    if sort == "rarity":
        rank = sql_case(
            *[
                (ItemDef.rarity == rarity, order)
                for rarity, order in RARITY_ORDER.items()
            ],
            else_=0,
        )
        # У предметов-кейсов ItemDef = NULL — кейсы в конце результата.
        query = query.order_by(
            nulls_last(rank.desc()),
            nulls_last(ItemDef.value.desc()),
            InventoryItem.id,
        )
    elif sort == "value":
        query = query.order_by(nulls_last(ItemDef.value.desc()), InventoryItem.id)
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
    for slot_name in LOADOUT_SLOTS:
        item = by_slot.get(slot_name)
        out[slot_name] = item_outs_by_id[item.id] if item is not None else None
    return LoadoutOut(**out, complete=len(by_slot) == 13)


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
        item_def = (
            await db.get(ItemDef, item.item_def_id) if item.item_def_id is not None else None
        )
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


@router.post("/upgrade/preview", response_model=UpgradePreviewOut)
async def preview(body: UpgradeIn, user: UserDep, db: DbDep) -> UpgradePreviewOut:
    return await upgrade_service.preview(db, user, body.input_ids, body.target_def_id)


@router.post("/upgrade", response_model=UpgradeOut)
async def run_upgrade(body: UpgradeIn, user: UserDep, db: DbDep) -> UpgradeOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await upgrade_service.execute(db, user, body.input_ids, body.target_def_id, clock.now())
