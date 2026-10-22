import app.core.clock as clock
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.core.errors import AppError
from app.db import get_db
from app.models import Case, CaseDrop, Collection, InventoryItem, ItemDef, User
from app.schemas.items import (
    AdminCaseOut,
    AdminCollectionDetailOut,
    AdminCollectionOut,
    AdminDropOut,
    AutoDropsIn,
    CaseCreateIn,
    CasePatchIn,
    CollectionCreateIn,
    CollectionPatchIn,
    DropsIn,
    GrantItemIn,
    ItemDefPatchIn,
    ItemDefOut,
    ItemOut,
)
from app.seed_data import CANONICAL_SLOTS
from app.services import catalog_admin as service
from app.services.cases import case_collections
from app.services.items import item_def_out, items_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]

_COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")
_CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")


def _collection_out(collection: Collection, items_count: int) -> AdminCollectionOut:
    return AdminCollectionOut(
        id=collection.id,
        code=collection.code,
        name=collection.name,
        description=collection.description,
        status=collection.status,
        created_at=collection.created_at,
        released_at=collection.released_at,
        retired_at=collection.retired_at,
        items_count=items_count,
    )


async def _collection_counts(db: AsyncSession) -> dict[int, int]:
    items = await db.execute(
        select(ItemDef.collection_id, func.count()).group_by(ItemDef.collection_id)
    )
    return dict(items.all())


async def _collection_detail(
    db: AsyncSession, collection: Collection
) -> AdminCollectionDetailOut:
    defs = list(
        (await db.scalars(select(ItemDef).where(ItemDef.collection_id == collection.id))).all()
    )
    defs.sort(key=lambda d: CANONICAL_SLOTS.index(d.side + d.piece_type))
    counts = await _collection_counts(db)
    return AdminCollectionDetailOut(
        **_collection_out(collection, counts.get(collection.id, 0)).model_dump(),
        items=[item_def_out(d, collection) for d in defs],
    )


@router.get("/collections", response_model=list[AdminCollectionOut])
async def list_collections(admin: AdminDep, db: DbDep) -> list[AdminCollectionOut]:
    collections = (await db.scalars(select(Collection).order_by(Collection.id))).all()
    counts = await _collection_counts(db)
    return [_collection_out(c, counts.get(c.id, 0)) for c in collections]


@router.get("/collections/{collection_id}", response_model=AdminCollectionDetailOut)
async def get_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionDetailOut:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise _COLLECTION_NOT_FOUND
    return await _collection_detail(db, collection)


@router.post("/collections", response_model=AdminCollectionDetailOut, status_code=201)
async def create_collection(
    body: CollectionCreateIn, admin: AdminDep, db: DbDep
) -> AdminCollectionDetailOut:
    collection = await service.create_collection(db, admin, body)
    return await _collection_detail(db, collection)


@router.patch("/collections/{collection_id}", response_model=AdminCollectionOut)
async def patch_collection(
    collection_id: int, body: CollectionPatchIn, admin: AdminDep, db: DbDep
) -> AdminCollectionOut:
    collection = await service.patch_collection(db, admin, collection_id, body)
    counts = await _collection_counts(db)
    return _collection_out(collection, counts.get(collection.id, 0))


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_collection(db, admin, collection_id)


@router.post("/collections/{collection_id}/release", response_model=AdminCollectionOut)
async def release_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionOut:
    collection = await service.release_collection(db, admin, collection_id, clock.now())
    counts = await _collection_counts(db)
    return _collection_out(collection, counts.get(collection.id, 0))


@router.post("/collections/{collection_id}/retire", response_model=AdminCollectionOut)
async def retire_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionOut:
    collection = await service.retire_collection(db, admin, collection_id, clock.now())
    counts = await _collection_counts(db)
    return _collection_out(collection, counts.get(collection.id, 0))


@router.get("/item-defs", response_model=list[ItemDefOut])
async def list_item_defs(admin: AdminDep, db: DbDep) -> list[ItemDefOut]:
    rows = await db.execute(
        select(ItemDef, Collection)
        .join(Collection, Collection.id == ItemDef.collection_id)
        .where(Collection.status != "retired")
        .order_by(ItemDef.collection_id, ItemDef.id)
    )
    return [item_def_out(def_, collection) for def_, collection in rows.all()]


@router.patch("/item-defs/{item_def_id}", response_model=ItemDefOut)
async def patch_item_def(
    item_def_id: int, body: ItemDefPatchIn, admin: AdminDep, db: DbDep
) -> ItemDefOut:
    item_def = await service.patch_item_def(db, admin, item_def_id, body)
    collection = await db.get(Collection, item_def.collection_id)
    return item_def_out(item_def, collection)


async def _get_case(db: AsyncSession, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise _CASE_NOT_FOUND
    return case


async def _case_out(db: AsyncSession, case: Case) -> AdminCaseOut:
    drops = (
        await db.scalars(
            select(CaseDrop).where(CaseDrop.case_id == case.id).order_by(CaseDrop.item_def_id)
        )
    ).all()
    collections = (await case_collections(db, [case.id]))[case.id]
    return AdminCaseOut(
        id=case.id,
        code=case.code,
        name=case.name,
        price=case.price,
        status=case.status,
        sort=case.sort,
        collections=collections,
        drops=[AdminDropOut(item_def_id=d.item_def_id, weight=d.weight) for d in drops],
    )


@router.get("/cases", response_model=list[AdminCaseOut])
async def list_cases(admin: AdminDep, db: DbDep) -> list[AdminCaseOut]:
    cases = (await db.scalars(select(Case).order_by(Case.sort, Case.id))).all()
    ids = [c.id for c in cases]
    drops_by_case: dict[int, list[CaseDrop]] = {}
    drops = (
        await db.scalars(
            select(CaseDrop)
            .where(CaseDrop.case_id.in_(ids))
            .order_by(CaseDrop.case_id, CaseDrop.item_def_id)
        )
    ).all()
    for drop in drops:
        drops_by_case.setdefault(drop.case_id, []).append(drop)
    colls = await case_collections(db, ids)
    return [
        AdminCaseOut(
            id=c.id,
            code=c.code,
            name=c.name,
            price=c.price,
            status=c.status,
            sort=c.sort,
            collections=colls.get(c.id, []),
            drops=[
                AdminDropOut(item_def_id=d.item_def_id, weight=d.weight)
                for d in drops_by_case.get(c.id, [])
            ],
        )
        for c in cases
    ]


@router.post("/cases", response_model=AdminCaseOut, status_code=201)
async def create_case(body: CaseCreateIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.create_case(db, admin, body)
    return AdminCaseOut(
        id=case.id,
        code=case.code,
        name=case.name,
        price=case.price,
        status=case.status,
        sort=case.sort,
        collections=[],
        drops=[],
    )


@router.patch("/cases/{case_id}", response_model=AdminCaseOut)
async def patch_case(case_id: int, body: CasePatchIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.patch_case(db, admin, case_id, body)
    return await _case_out(db, case)


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(case_id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_case(db, admin, case_id)


@router.put("/cases/{case_id}/drops", response_model=AdminCaseOut)
async def set_drops(case_id: int, body: DropsIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.set_drops(db, admin, case_id, body.root)
    return await _case_out(db, case)


@router.post("/cases/{case_id}/drops/auto", response_model=AdminCaseOut)
async def auto_drops(case_id: int, body: AutoDropsIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.auto_drops(db, admin, case_id, body.collection_ids)
    return await _case_out(db, case)


@router.post("/cases/{case_id}/activate", response_model=AdminCaseOut)
async def activate_case(case_id: int, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.activate_case(db, admin, case_id)
    return await _case_out(db, case)


@router.post("/cases/{case_id}/close", response_model=AdminCaseOut)
async def close_case(case_id: int, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    case = await service.close_case(db, admin, case_id)
    return await _case_out(db, case)


@router.post("/users/{user_id}/grant-item", response_model=ItemOut)
async def grant_item(user_id: int, body: GrantItemIn, admin: AdminDep, db: DbDep) -> ItemOut:
    item_id = await service.grant_item(db, admin, user_id, body.item_def_id, clock.now())
    item = await db.get(InventoryItem, item_id)
    return (await items_out(db, [item]))[0]
