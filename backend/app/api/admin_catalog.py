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
    CollectionRef,
    DropsIn,
    GrantItemIn,
    ItemDefCreateIn,
    ItemDefPatchIn,
    ItemDefOut,
    ItemOut,
    RARITY_ORDER,
)
from app.services import catalog_admin as service
from app.services.items import item_def_out, items_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin-catalog"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]

_COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")


def _collection_out(collection: Collection, items_count: int, cases_count: int) -> AdminCollectionOut:
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
        cases_count=cases_count,
    )


async def _collection_counts(db: AsyncSession) -> tuple[dict[int, int], dict[int, int]]:
    items = await db.execute(
        select(ItemDef.collection_id, func.count()).group_by(ItemDef.collection_id)
    )
    cases = await db.execute(
        select(Case.collection_id, func.count()).group_by(Case.collection_id)
    )
    return dict(items.all()), dict(cases.all())


@router.get("/collections", response_model=list[AdminCollectionOut])
async def list_collections(admin: AdminDep, db: DbDep) -> list[AdminCollectionOut]:
    collections = (await db.scalars(select(Collection).order_by(Collection.id))).all()
    items_counts, cases_counts = await _collection_counts(db)
    return [
        _collection_out(c, items_counts.get(c.id, 0), cases_counts.get(c.id, 0))
        for c in collections
    ]


@router.get("/collections/{collection_id}", response_model=AdminCollectionDetailOut)
async def get_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionDetailOut:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise _COLLECTION_NOT_FOUND
    defs = list(
        (await db.scalars(select(ItemDef).where(ItemDef.collection_id == collection.id))).all()
    )
    defs.sort(key=lambda d: (RARITY_ORDER[d.rarity], d.code))
    cases = (
        await db.scalars(select(Case).where(Case.collection_id == collection.id).order_by(Case.id))
    ).all()
    case_outs: list[AdminCaseOut] = []
    for case in cases:
        drops = (
            await db.scalars(
                select(CaseDrop)
                .where(CaseDrop.case_id == case.id)
                .order_by(CaseDrop.item_def_id)
            )
        ).all()
        case_outs.append(
            AdminCaseOut(
                id=case.id,
                code=case.code,
                name=case.name,
                price=case.price,
                collection=CollectionRef(code=collection.code, name=collection.name),
                is_active=case.is_active,
                sort=case.sort,
                drops=[AdminDropOut(item_def_id=d.item_def_id, weight=d.weight) for d in drops],
            )
        )
    items_counts, cases_counts = await _collection_counts(db)
    return AdminCollectionDetailOut(
        **_collection_out(collection, items_counts.get(collection.id, 0),
                          cases_counts.get(collection.id, 0)).model_dump(),
        items=[item_def_out(d, collection) for d in defs],
        cases=case_outs,
    )


@router.post("/collections", response_model=AdminCollectionOut, status_code=201)
async def create_collection(
    body: CollectionCreateIn, admin: AdminDep, db: DbDep
) -> AdminCollectionOut:
    collection = await service.create_collection(db, admin, body)
    return _collection_out(collection, 0, 0)


@router.patch("/collections/{collection_id}", response_model=AdminCollectionOut)
async def patch_collection(
    collection_id: int, body: CollectionPatchIn, admin: AdminDep, db: DbDep
) -> AdminCollectionOut:
    collection = await service.patch_collection(db, admin, collection_id, body)
    items_counts, cases_counts = await _collection_counts(db)
    return _collection_out(collection, items_counts.get(collection.id, 0), cases_counts.get(collection.id, 0))


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_collection(db, admin, collection_id)


@router.post("/collections/{collection_id}/release", response_model=AdminCollectionOut)
async def release_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionOut:
    collection = await service.release_collection(db, admin, collection_id, clock.now())
    items_counts, cases_counts = await _collection_counts(db)
    return _collection_out(collection, items_counts.get(collection.id, 0), cases_counts.get(collection.id, 0))


@router.post("/collections/{collection_id}/retire", response_model=AdminCollectionOut)
async def retire_collection(collection_id: int, admin: AdminDep, db: DbDep) -> AdminCollectionOut:
    collection = await service.retire_collection(db, admin, collection_id, clock.now())
    items_counts, cases_counts = await _collection_counts(db)
    return _collection_out(collection, items_counts.get(collection.id, 0), cases_counts.get(collection.id, 0))


@router.post("/collections/{collection_id}/items", response_model=ItemDefOut, status_code=201)
async def create_item_def(
    collection_id: int, body: ItemDefCreateIn, admin: AdminDep, db: DbDep
) -> ItemDefOut:
    item_def = await service.create_item_def(db, admin, collection_id, body)
    collection = await db.get(Collection, item_def.collection_id)
    return item_def_out(item_def, collection)


@router.patch("/item-defs/{item_def_id}", response_model=ItemDefOut)
async def patch_item_def(
    item_def_id: int, body: ItemDefPatchIn, admin: AdminDep, db: DbDep
) -> ItemDefOut:
    item_def = await service.patch_item_def(db, admin, item_def_id, body)
    collection = await db.get(Collection, item_def.collection_id)
    return item_def_out(item_def, collection)


@router.delete("/item-defs/{item_def_id}", status_code=204)
async def delete_item_def(item_def_id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_item_def(db, admin, item_def_id)


def _case_out(case: Case, collection: Collection, drops: list[CaseDrop]) -> AdminCaseOut:
    return AdminCaseOut(
        id=case.id,
        code=case.code,
        name=case.name,
        price=case.price,
        collection=CollectionRef(code=collection.code, name=collection.name),
        is_active=case.is_active,
        sort=case.sort,
        drops=[AdminDropOut(item_def_id=d.item_def_id, weight=d.weight) for d in drops],
    )


async def _load_case(db: AsyncSession, case_id: int) -> tuple[Case, Collection, list[CaseDrop]]:
    case = await db.get(Case, case_id)
    if case is None:
        raise AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
    collection = await db.get(Collection, case.collection_id)
    drops = list(
        (
            await db.scalars(
                select(CaseDrop).where(CaseDrop.case_id == case.id).order_by(CaseDrop.item_def_id)
            )
        ).all()
    )
    return case, collection, drops


@router.post("/collections/{collection_id}/cases", response_model=AdminCaseOut, status_code=201)
async def create_case(
    collection_id: int, body: CaseCreateIn, admin: AdminDep, db: DbDep
) -> AdminCaseOut:
    case = await service.create_case(db, admin, collection_id, body)
    collection = await db.get(Collection, case.collection_id)
    return _case_out(case, collection, [])


@router.patch("/cases/{case_id}", response_model=AdminCaseOut)
async def patch_case(case_id: int, body: CasePatchIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    await service.patch_case(db, admin, case_id, body)
    case, collection, drops = await _load_case(db, case_id)
    return _case_out(case, collection, drops)


@router.delete("/cases/{case_id}", status_code=204)
async def delete_case(case_id: int, admin: AdminDep, db: DbDep) -> None:
    await service.delete_case(db, admin, case_id)


@router.put("/cases/{case_id}/drops", response_model=AdminCaseOut)
async def set_drops(case_id: int, body: DropsIn, admin: AdminDep, db: DbDep) -> AdminCaseOut:
    await service.set_drops(db, admin, case_id, body.root)
    case, collection, drops = await _load_case(db, case_id)
    return _case_out(case, collection, drops)


@router.post("/cases/{case_id}/drops/auto", response_model=AdminCaseOut)
async def auto_drops(
    case_id: int, admin: AdminDep, db: DbDep, body: AutoDropsIn | None = None
) -> AdminCaseOut:
    kind = body.kind if body is not None else None
    await service.auto_drops(db, admin, case_id, kind)
    case, collection, drops = await _load_case(db, case_id)
    return _case_out(case, collection, drops)


@router.post("/users/{user_id}/grant-item", response_model=ItemOut)
async def grant_item(user_id: int, body: GrantItemIn, admin: AdminDep, db: DbDep) -> ItemOut:
    item_id = await service.grant_item(db, admin, user_id, body.item_def_id, clock.now())
    item = await db.get(InventoryItem, item_id)
    return (await items_out(db, [item]))[0]
