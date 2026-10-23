from typing import Annotated, Any

import app.core.clock as clock
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.errors import AppError
from app.db import get_db
from app.models import (
    Case,
    CaseDrop,
    Collection,
    DailyRewardPool,
    InventoryItem,
    ItemDef,
    ItemSet,
    User,
)
from app.schemas.items import (
    AdminCaseOut,
    AdminDropOut,
    AdminSetCollectionOut,
    AdminSetDetailOut,
    AdminSetOut,
    AutoDropsIn,
    BoardCreateIn,
    CaseCreateIn,
    CasePatchIn,
    CaseRefOut,
    CollectionCreateIn,
    CollectionPatchIn,
    CollectionRef,
    DailyPoolEntryOut,
    DailyPoolIn,
    DropsIn,
    GrantItemIn,
    ItemDefOut,
    ItemDefPatchIn,
    ItemOut,
    SetCreateIn,
    SetPatchIn,
    SetRef,
)
from app.seed_data import CANONICAL_SLOTS
from app.services import catalog_admin as service
from app.services.cases import on_sale_now
from app.services.items import case_ref_out, item_def_out, items_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]

_SET_NOT_FOUND = AppError(404, "SET_NOT_FOUND", "Набор не найден")
_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")


async def _get(
    db: AsyncSession, model: type[Any], obj_id: int, error: AppError
) -> Any:
    obj = await db.get(model, obj_id)
    if obj is None:
        raise error
    return obj


async def _set_out(db: AsyncSession, s: ItemSet) -> AdminSetOut:
    collections_count = (
        await db.scalar(
            select(func.count())
            .select_from(Collection)
            .where(Collection.set_id == s.id)
        )
        or 0
    )
    boards_count = (
        await db.scalar(
            select(func.count())
            .select_from(ItemDef)
            .where(ItemDef.set_id == s.id, ItemDef.kind == "board")
        )
        or 0
    )
    return AdminSetOut(
        id=s.id,
        code=s.code,
        name=s.name,
        description=s.description,
        status=s.status,
        is_base=s.is_base,
        created_at=s.created_at,
        released_at=s.released_at,
        retired_at=s.retired_at,
        collections_count=int(collections_count),
        boards_count=int(boards_count),
    )


async def _set_detail(db: AsyncSession, s: ItemSet) -> AdminSetDetailOut:
    collections = list(
        (
            await db.scalars(
                select(Collection)
                .where(Collection.set_id == s.id)
                .order_by(Collection.id)
            )
        ).all()
    )
    defs_by_collection: dict[int, list[ItemDef]] = {c.id: [] for c in collections}
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
            defs_by_collection[d.collection_id].append(d)
    for defs_list in defs_by_collection.values():
        defs_list.sort(
            key=lambda d: CANONICAL_SLOTS.index(str(d.side) + str(d.piece_type))
        )
    coll_by_id = {c.id: c for c in collections}
    collections_out = [
        AdminSetCollectionOut(
            id=c.id,
            code=c.code,
            name=c.name,
            description=c.description,
            items=[
                item_def_out(d, s, coll_by_id[d.collection_id])
                for d in defs_by_collection[c.id]
            ],
        )
        for c in collections
    ]
    boards = list(
        (
            await db.scalars(
                select(ItemDef)
                .where(ItemDef.set_id == s.id, ItemDef.kind == "board")
                .order_by(ItemDef.id)
            )
        ).all()
    )
    return AdminSetDetailOut(
        **(await _set_out(db, s)).model_dump(),
        collections=collections_out,
        boards=[item_def_out(b, s, None) for b in boards],
    )


async def _cases_out(
    db: AsyncSession, cases: list[Case]
) -> list[AdminCaseOut]:
    if not cases:
        return []
    now = clock.now()
    case_ids = [c.id for c in cases]
    set_ids = {c.set_id for c in cases if c.set_id is not None}
    sets: dict[int, ItemSet] = {}
    if set_ids:
        sets = {
            s.id: s
            for s in (
                await db.scalars(select(ItemSet).where(ItemSet.id.in_(set_ids)))
            ).all()
        }
    collection_ids = {c.collection_id for c in cases if c.collection_id is not None}
    collections: dict[int, Collection] = {}
    if collection_ids:
        collections = {
            c.id: c
            for c in (
                await db.scalars(
                    select(Collection).where(Collection.id.in_(collection_ids))
                )
            ).all()
        }
    drops_by_case: dict[int, list[CaseDrop]] = {}
    drops = list(
        (
            await db.scalars(
                select(CaseDrop)
                .where(CaseDrop.case_id.in_(case_ids))
                .order_by(CaseDrop.case_id, CaseDrop.item_def_id)
            )
        ).all()
    )
    for drop in drops:
        drops_by_case.setdefault(drop.case_id, []).append(drop)
    outs: list[AdminCaseOut] = []
    for case in cases:
        item_set = sets.get(case.set_id) if case.set_id is not None else None
        collection = (
            collections.get(case.collection_id)
            if case.collection_id is not None
            else None
        )
        outs.append(
            AdminCaseOut(
                id=case.id,
                code=case.code,
                name=case.name,
                kind=case.kind,
                set=SetRef(code=item_set.code, name=item_set.name)
                if item_set is not None
                else None,
                collection=CollectionRef(code=collection.code, name=collection.name)
                if collection is not None
                else None,
                price=case.price,
                sort=case.sort,
                status=case.status,
                stock_limit=case.stock_limit,
                sold_count=case.sold_count,
                sale_starts_at=case.sale_starts_at,
                sale_ends_at=case.sale_ends_at,
                on_sale_now=on_sale_now(case, now),
                drops=[
                    AdminDropOut(item_def_id=d.item_def_id, weight=d.weight)
                    for d in drops_by_case.get(case.id, [])
                ],
            )
        )
    return outs


# --- Наборы -------------------------------------------------------------------


@router.get("/sets", response_model=list[AdminSetOut])
async def list_sets(admin: AdminDep, db: DbDep) -> list[AdminSetOut]:
    sets = list(
        (await db.scalars(select(ItemSet).order_by(ItemSet.id))).all()
    )
    return [await _set_out(db, s) for s in sets]


@router.post("/sets", response_model=AdminSetOut, status_code=201)
async def create_set(body: SetCreateIn, admin: AdminDep, db: DbDep) -> AdminSetOut:
    item_set = await service.create_set(db, admin, body)
    return await _set_out(db, item_set)


@router.get("/sets/{id}", response_model=AdminSetDetailOut)
async def get_set(id: int, admin: AdminDep, db: DbDep) -> AdminSetDetailOut:
    item_set = await _get(db, ItemSet, id, _SET_NOT_FOUND)
    return await _set_detail(db, item_set)


@router.patch("/sets/{id}", response_model=AdminSetOut)
async def patch_set(
    id: int, body: SetPatchIn, admin: AdminDep, db: DbDep
) -> AdminSetOut:
    item_set = await service.patch_set(db, admin, id, body)
    return await _set_out(db, item_set)


@router.delete("/sets/{id}", status_code=204)
async def delete_set(id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_set(db, admin, id)


@router.post("/sets/{id}/release", response_model=AdminSetOut)
async def release_set(id: int, admin: AdminDep, db: DbDep) -> AdminSetOut:
    item_set = await service.release_set(db, admin, id, clock.now())
    return await _set_out(db, item_set)


@router.post("/sets/{id}/retire", response_model=AdminSetOut)
async def retire_set(id: int, admin: AdminDep, db: DbDep) -> AdminSetOut:
    item_set = await service.retire_set(db, admin, id, clock.now())
    return await _set_out(db, item_set)


# --- Коллекции ----------------------------------------------------------------


@router.post("/sets/{id}/collections", response_model=AdminSetDetailOut, status_code=201)
async def create_collection(
    id: int, body: CollectionCreateIn, admin: AdminDep, db: DbDep
) -> AdminSetDetailOut:
    await service.create_collection(db, admin, id, body)
    item_set = await _get(db, ItemSet, id, _SET_NOT_FOUND)
    return await _set_detail(db, item_set)


@router.patch("/collections/{id}", response_model=AdminSetDetailOut)
async def patch_collection(
    id: int, body: CollectionPatchIn, admin: AdminDep, db: DbDep
) -> AdminSetDetailOut:
    collection = await service.patch_collection(db, admin, id, body)
    item_set = await _get(db, ItemSet, collection.set_id, _SET_NOT_FOUND)
    return await _set_detail(db, item_set)


@router.delete("/collections/{id}", status_code=204)
async def delete_collection(id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_collection(db, admin, id)


# --- Доски и скины ------------------------------------------------------------


@router.post("/sets/{id}/boards", response_model=ItemDefOut, status_code=201)
async def create_board(
    id: int, body: BoardCreateIn, admin: AdminDep, db: DbDep
) -> ItemDefOut:
    item_def = await service.create_board(db, admin, id, body)
    item_set = await _get(db, ItemSet, item_def.set_id, _SET_NOT_FOUND)
    return item_def_out(item_def, item_set, None)


@router.get("/item-defs", response_model=list[ItemDefOut])
async def list_item_defs(admin: AdminDep, db: DbDep) -> list[ItemDefOut]:
    rows = await db.execute(
        select(ItemDef, ItemSet, Collection)
        .join(ItemSet, ItemSet.id == ItemDef.set_id)
        .outerjoin(Collection, Collection.id == ItemDef.collection_id)
        .where(ItemSet.is_base == False, ItemSet.status != "retired")  # noqa: E712
        .order_by(ItemDef.set_id, ItemDef.id)
    )
    return [item_def_out(d, s, c) for d, s, c in rows.all()]


@router.patch("/item-defs/{id}", response_model=ItemDefOut)
async def patch_item_def(
    id: int, body: ItemDefPatchIn, admin: AdminDep, db: DbDep
) -> ItemDefOut:
    item_def = await service.patch_item_def(db, admin, id, body)
    item_set = await _get(db, ItemSet, item_def.set_id, _SET_NOT_FOUND)
    collection = (
        await db.get(Collection, item_def.collection_id)
        if item_def.collection_id is not None
        else None
    )
    return item_def_out(item_def, item_set, collection)


@router.delete("/item-defs/{id}", status_code=204)
async def delete_item_def(id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_item_def(db, admin, id)


# --- Кейсы --------------------------------------------------------------------


@router.get("/cases", response_model=list[AdminCaseOut])
async def list_cases(admin: AdminDep, db: DbDep) -> list[AdminCaseOut]:
    cases = list(
        (await db.scalars(select(Case).order_by(Case.sort, Case.id))).all()
    )
    return await _cases_out(db, cases)


@router.post("/cases", response_model=AdminCaseOut, status_code=201)
async def create_case(body: CaseCreateIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.create_case(db, admin, body)
    return (await _cases_out(db, [case]))[0]


@router.patch("/cases/{id}", response_model=AdminCaseOut)
async def patch_case(id: int, body: CasePatchIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.patch_case(db, admin, id, body)
    return (await _cases_out(db, [case]))[0]


@router.delete("/cases/{id}", status_code=204)
async def delete_case(id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_case(db, admin, id)


@router.put("/cases/{id}/drops", response_model=AdminCaseOut)
async def set_drops(id: int, body: DropsIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.set_drops(db, admin, id, body.root)
    return (await _cases_out(db, [case]))[0]


@router.post("/cases/{id}/drops/auto", response_model=AdminCaseOut)
async def auto_drops(id: int, body: AutoDropsIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.auto_drops(db, admin, id, body.set_ids, body.collection_ids)
    return (await _cases_out(db, [case]))[0]


@router.post("/cases/{id}/publish", response_model=AdminCaseOut)
async def publish_case(id: int, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.publish_case(db, admin, id, clock.now())
    return (await _cases_out(db, [case]))[0]


@router.post("/cases/{id}/unpublish", response_model=AdminCaseOut)
async def unpublish_case(id: int, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.unpublish_case(db, admin, id)
    return (await _cases_out(db, [case]))[0]


# --- Пул ежедневной награды ---------------------------------------------------


async def _pool_outs(db: AsyncSession) -> list[DailyPoolEntryOut]:
    rows = await db.execute(
        select(DailyRewardPool, Case)
        .join(Case, Case.id == DailyRewardPool.case_id)
        .order_by(DailyRewardPool.case_id)
    )
    return [
        DailyPoolEntryOut(case=case_ref_out(case), weight=pool.weight)
        for pool, case in rows.all()
    ]


@router.get("/daily-reward-pool", response_model=list[DailyPoolEntryOut])
async def get_daily_pool(admin: AdminDep, db: DbDep) -> list[DailyPoolEntryOut]:
    return await _pool_outs(db)


@router.put("/daily-reward-pool", response_model=list[DailyPoolEntryOut])
async def put_daily_pool(
    body: DailyPoolIn, admin: AdminDep, db: DbDep
) -> list[DailyPoolEntryOut]:
    await service.set_daily_pool(db, admin, body.root)
    return await _pool_outs(db)


# --- Выдача предмета ----------------------------------------------------------


@router.post("/users/{id}/grant-item", response_model=ItemOut)
async def grant_item(id: int, body: GrantItemIn, admin: AdminDep, db: DbDep) -> ItemOut:
    item_id = await service.grant_item(
        db, admin, id, body.item_def_id, body.case_id, clock.now()
    )
    item = await db.get(InventoryItem, item_id)
    return (await items_out(db, [item]))[0]
