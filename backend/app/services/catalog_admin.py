import app.core.clock as clock
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AdminAudit, Case, CaseDrop, Collection, ItemDef, User
from app.schemas.items import (
    CaseCreateIn,
    CasePatchIn,
    CollectionCreateIn,
    CollectionPatchIn,
    DropIn,
    ItemDefPatchIn,
)
from app.seed_data import item_code, item_name
from app.services.cases import auto_weights
from app.services.items import create_item
from app.services.settings import get_setting

COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")
ITEM_DEF_NOT_FOUND = AppError(404, "ITEM_DEF_NOT_FOUND", "Скин не найден")
CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")

COLLECTION_CODE_TAKEN = AppError(409, "COLLECTION_CODE_TAKEN", "Код коллекции занят")
ITEM_CODE_TAKEN = AppError(409, "ITEM_CODE_TAKEN", "Код скина занят")
CASE_CODE_TAKEN = AppError(409, "CASE_CODE_TAKEN", "Код кейса занят")

COLLECTION_NOT_DRAFT = AppError(400, "COLLECTION_NOT_DRAFT", "Действие только для черновика")
COLLECTION_NOT_RELEASED = AppError(400, "COLLECTION_NOT_RELEASED", "Снять можно только выпущенную")
ITEM_DEF_LOCKED = AppError(
    400, "ITEM_DEF_LOCKED", "После выпуска можно менять только name, asset, value, is_upgrade_target"
)
ITEM_DEF_NOT_AVAILABLE = AppError(
    400, "ITEM_DEF_NOT_AVAILABLE", "Скин не из выпущенной коллекции"
)

CASE_LOCKED = AppError(400, "CASE_LOCKED", "Дропы можно менять только у черновика кейса")
CASE_NOT_READY = AppError(
    400, "CASE_NOT_READY", "Кейс не готов: нет дропов или есть скины невыпущенных коллекций"
)
CASE_NOT_ACTIVE = AppError(400, "CASE_NOT_ACTIVE", "Кейс не активен")
DROP_ITEM_NOT_AVAILABLE = AppError(400, "DROP_ITEM_NOT_AVAILABLE", "Скин недоступен для кейса")


def _audit(
    db: AsyncSession, admin: User, action: str, target: str, payload: object
) -> None:
    db.add(
        AdminAudit(
            admin_id=admin.id,
            action=action,
            target=target,
            payload=payload,
        )
    )


# --- Коллекции ---------------------------------------------------------------


async def create_collection(
    db: AsyncSession, admin: User, body: CollectionCreateIn
) -> Collection:
    collection = Collection(
        code=body.code,
        name=body.name,
        description=body.description,
        status="draft",
    )
    db.add(collection)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise COLLECTION_CODE_TAKEN from exc

    for p in body.pieces:
        db.add(
            ItemDef(
                collection_id=collection.id,
                code=item_code(body.code, p.side, p.piece_type),
                name=item_name(body.name, p.side, p.piece_type),
                side=p.side,
                piece_type=p.piece_type,
                rarity=p.rarity,
                value=p.value,
                asset=p.asset.model_dump(),
                is_upgrade_target=p.is_upgrade_target,
            )
        )
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ITEM_CODE_TAKEN from exc

    _audit(db, admin, "collection.create", f"collection:{collection.id}", body.model_dump(mode="json"))
    return collection


async def patch_collection(
    db: AsyncSession, admin: User, collection_id: int, body: CollectionPatchIn
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    fields = body.model_fields_set
    if "name" in fields:
        collection.name = body.name
    if "description" in fields:
        collection.description = body.description
    _audit(
        db, admin, "collection.patch", f"collection:{collection.id}", body.model_dump(mode="json", exclude_unset=True)
    )
    return collection


async def delete_collection(db: AsyncSession, admin: User, collection_id: int) -> None:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    if collection.status != "draft":
        raise COLLECTION_NOT_DRAFT
    def_ids = select(ItemDef.id).where(ItemDef.collection_id == collection.id)
    await db.execute(delete(CaseDrop).where(CaseDrop.item_def_id.in_(def_ids)))
    await db.execute(delete(ItemDef).where(ItemDef.collection_id == collection.id))
    await db.delete(collection)
    _audit(db, admin, "collection.delete", f"collection:{collection_id}", {})


async def release_collection(
    db: AsyncSession, admin: User, collection_id: int, now: datetime
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    if collection.status != "draft":
        raise COLLECTION_NOT_DRAFT
    collection.status = "released"
    collection.released_at = now
    _audit(db, admin, "collection.release", f"collection:{collection.id}", {})
    return collection


async def retire_collection(
    db: AsyncSession, admin: User, collection_id: int, now: datetime
) -> Collection:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    if collection.status != "released":
        raise COLLECTION_NOT_RELEASED
    ids = list(
        (
            await db.scalars(
                select(Case.id)
                .join(CaseDrop, CaseDrop.case_id == Case.id)
                .join(ItemDef, ItemDef.id == CaseDrop.item_def_id)
                .where(ItemDef.collection_id == collection.id, Case.status == "active")
                .distinct()
                .order_by(Case.id)
            )
        ).all()
    )
    if ids:
        await db.execute(update(Case).where(Case.id.in_(ids)).values(status="closed"))
    collection.status = "retired"
    collection.retired_at = now
    _audit(
        db, admin, "collection.retire", f"collection:{collection.id}", {"closed_case_ids": ids}
    )
    return collection


# --- Скины -------------------------------------------------------------------


async def patch_item_def(
    db: AsyncSession, admin: User, item_def_id: int, body: ItemDefPatchIn
) -> ItemDef:
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    collection = await db.get(Collection, item_def.collection_id)
    released = collection is not None and collection.status != "draft"
    fields = body.model_fields_set
    if released and "rarity" in fields:
        raise ITEM_DEF_LOCKED

    if "name" in fields:
        item_def.name = body.name
    if "rarity" in fields:
        item_def.rarity = body.rarity
    if "value" in fields:
        item_def.value = body.value
    if "asset" in fields:
        item_def.asset = body.asset.model_dump()
    if "is_upgrade_target" in fields:
        item_def.is_upgrade_target = bool(body.is_upgrade_target)
    _audit(
        db, admin, "item_def.patch", f"item_def:{item_def.id}", body.model_dump(mode="json", exclude_unset=True)
    )
    return item_def


# --- Кейсы -------------------------------------------------------------------


async def create_case(db: AsyncSession, admin: User, body: CaseCreateIn) -> Case:
    case = Case(
        code=body.code,
        name=body.name,
        price=body.price,
        sort=body.sort,
        status="draft",
    )
    db.add(case)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise CASE_CODE_TAKEN from exc
    _audit(db, admin, "case.create", f"case:{case.id}", body.model_dump(mode="json"))
    return case


async def patch_case(db: AsyncSession, admin: User, case_id: int, body: CasePatchIn) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    fields = body.model_fields_set
    if "name" in fields:
        case.name = body.name
    if "price" in fields:
        case.price = body.price
    if "sort" in fields:
        case.sort = body.sort
    _audit(
        db, admin, "case.patch", f"case:{case.id}", body.model_dump(mode="json", exclude_unset=True)
    )
    return case


async def delete_case(db: AsyncSession, admin: User, case_id: int) -> None:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status != "draft":
        raise CASE_LOCKED
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    await db.delete(case)
    _audit(db, admin, "case.delete", f"case:{case_id}", {})


async def _draft_case(db: AsyncSession, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status != "draft":
        raise CASE_LOCKED
    return case


async def _check_available_defs(db: AsyncSession, def_ids: list[int]) -> None:
    rows = (
        await db.execute(
            select(ItemDef.id, Collection.status)
            .join(Collection, Collection.id == ItemDef.collection_id)
            .where(ItemDef.id.in_(def_ids))
        )
    ).all()
    found_ids = {row[0] for row in rows}
    if len(found_ids) < len(def_ids) or any(row[1] == "retired" for row in rows):
        raise DROP_ITEM_NOT_AVAILABLE


async def set_drops(
    db: AsyncSession, admin: User, case_id: int, drops: list[DropIn]
) -> Case:
    case = await _draft_case(db, case_id)
    await _check_available_defs(db, [d.item_def_id for d in drops])
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    for drop in drops:
        db.add(
            CaseDrop(case_id=case.id, item_def_id=drop.item_def_id, weight=drop.weight)
        )
    await db.flush()
    _audit(
        db,
        admin,
        "case.drops.set",
        f"case:{case.id}",
        {"drops": [d.model_dump(mode="json") for d in drops]},
    )
    return case


async def auto_drops(
    db: AsyncSession, admin: User, case_id: int, collection_ids: list[int]
) -> Case:
    case = await _draft_case(db, case_id)
    collections = list(
        (await db.scalars(select(Collection).where(Collection.id.in_(collection_ids)))).all()
    )
    if len(collections) < len(collection_ids):
        raise COLLECTION_NOT_FOUND
    if any(c.status == "retired" for c in collections):
        raise DROP_ITEM_NOT_AVAILABLE
    skins = list(
        (
            await db.scalars(select(ItemDef).where(ItemDef.collection_id.in_(collection_ids)))
        ).all()
    )
    weights = auto_weights(skins, await get_setting(db, "rarity_weights"))
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    for item_def_id, weight in weights.items():
        db.add(CaseDrop(case_id=case.id, item_def_id=item_def_id, weight=weight))
    await db.flush()
    _audit(db, admin, "case.drops.auto", f"case:{case.id}", {"collection_ids": collection_ids})
    return case


async def activate_case(db: AsyncSession, admin: User, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status == "active":
        raise CASE_NOT_READY
    drops_count = await db.scalar(
        select(func.count()).select_from(CaseDrop).where(CaseDrop.case_id == case.id)
    )
    if (drops_count or 0) < 1:
        raise CASE_NOT_READY
    not_released_count = await db.scalar(
        select(func.count())
        .select_from(CaseDrop)
        .join(ItemDef, ItemDef.id == CaseDrop.item_def_id)
        .join(Collection, Collection.id == ItemDef.collection_id)
        .where(CaseDrop.case_id == case.id, Collection.status != "released")
    )
    if (not_released_count or 0) > 0:
        raise CASE_NOT_READY
    case.status = "active"
    _audit(db, admin, "case.activate", f"case:{case.id}", {})
    return case


async def close_case(db: AsyncSession, admin: User, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status != "active":
        raise CASE_NOT_ACTIVE
    case.status = "closed"
    _audit(db, admin, "case.close", f"case:{case.id}", {})
    return case


# --- Выдача предмета ---------------------------------------------------------


async def grant_item(
    db: AsyncSession, admin: User, user_id: int, item_def_id: int, now: datetime
) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    collection = await db.get(Collection, item_def.collection_id)
    if collection is None or collection.status != "released":
        raise ITEM_DEF_NOT_AVAILABLE
    item = await create_item(
        db,
        user_id=user.id,
        def_id=item_def.id,
        source="admin_grant",
        source_ref=str(admin.id),
        now=now,
    )
    _audit(db, admin, "user.grant_item", f"user:{user.id}", {"item_def_id": item_def_id})
    return item.id
