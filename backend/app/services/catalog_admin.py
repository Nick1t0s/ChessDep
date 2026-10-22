import app.core.clock as clock
from datetime import datetime

from sqlalchemy import delete, func, select
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
    ItemDefCreateIn,
    ItemDefPatchIn,
    PieceAsset,
    BoardAsset,
)
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
COLLECTION_NOT_READY = AppError(
    400, "COLLECTION_NOT_READY", "Коллекция не готова к выпуску: нет скинов или у кейса нет дропов"
)
COLLECTION_NOT_RELEASED = AppError(400, "COLLECTION_NOT_RELEASED", "Снять можно только выпущенную")
ITEM_DEF_LOCKED = AppError(
    400, "ITEM_DEF_LOCKED", "После выпуска можно менять только name, asset, value, is_upgrade_target"
)
CASE_LOCKED = AppError(400, "CASE_LOCKED", "После выпуска коллекции дропы кейса изменять нельзя")
DROP_ITEM_NOT_IN_COLLECTION = AppError(
    400, "DROP_ITEM_NOT_IN_COLLECTION", "Скин не принадлежит коллекции кейса"
)
ITEM_DEF_NOT_AVAILABLE = AppError(
    400, "ITEM_DEF_NOT_AVAILABLE", "Скин не из выпущенной коллекции"
)
ASSET_KIND_MISMATCH = AppError(422, "VALIDATION_ERROR", "asset не соответствует виду скина")
PIECE_TYPE_REQUIRED = AppError(
    422, "VALIDATION_ERROR", "piece_type обязателен для piece_skin"
)


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
    case_ids = select(Case.id).where(Case.collection_id == collection.id)
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id.in_(case_ids)))
    await db.execute(delete(Case).where(Case.collection_id == collection.id))
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
    skins_count = await db.scalar(
        select(func.count()).select_from(ItemDef).where(ItemDef.collection_id == collection.id)
    )
    if (skins_count or 0) < 1:
        raise COLLECTION_NOT_READY
    cases = (await db.scalars(select(Case).where(Case.collection_id == collection.id))).all()
    for case in cases:
        drops_count = await db.scalar(
            select(func.count()).select_from(CaseDrop).where(CaseDrop.case_id == case.id)
        )
        if (drops_count or 0) < 1:
            raise COLLECTION_NOT_READY
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
    collection.status = "retired"
    collection.retired_at = now
    _audit(db, admin, "collection.retire", f"collection:{collection.id}", {})
    return collection


# --- Скины -------------------------------------------------------------------


async def create_item_def(
    db: AsyncSession, admin: User, collection_id: int, body: ItemDefCreateIn
) -> ItemDef:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    item_def = ItemDef(
        collection_id=collection.id,
        code=body.code,
        name=body.name,
        kind=body.kind,
        piece_type=body.piece_type,
        rarity=body.rarity,
        value=body.value,
        asset=body.asset.model_dump(),
        is_upgrade_target=body.is_upgrade_target,
    )
    db.add(item_def)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ITEM_CODE_TAKEN from exc
    _audit(
        db, admin, "item_def.create", f"item_def:{item_def.id}", body.model_dump(mode="json")
    )
    return item_def


def _asset_matches_kind(asset: dict, kind: str) -> bool:
    try:
        if kind == "piece_skin":
            PieceAsset.model_validate(asset)
        else:
            BoardAsset.model_validate(asset)
    except Exception:
        return False
    return True


async def patch_item_def(
    db: AsyncSession, admin: User, item_def_id: int, body: ItemDefPatchIn
) -> ItemDef:
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    collection = await db.get(Collection, item_def.collection_id)
    released = collection is not None and collection.status != "draft"
    fields = body.model_fields_set
    locked_fields = {"kind", "piece_type", "rarity"}
    if released and (fields & locked_fields):
        raise ITEM_DEF_LOCKED

    kind = body.kind if "kind" in fields else item_def.kind
    piece_type = body.piece_type if "piece_type" in fields else item_def.piece_type
    if kind == "piece_skin":
        if piece_type is None:
            raise PIECE_TYPE_REQUIRED
    else:
        # board_skin: piece_type сбрасывается в NULL.
        piece_type = None
    if "asset" in fields:
        asset = body.asset.model_dump()
    else:
        asset = item_def.asset
    if not _asset_matches_kind(asset, kind):
        raise ASSET_KIND_MISMATCH

    if "name" in fields:
        item_def.name = body.name
    if "kind" in fields:
        item_def.kind = kind
    if "piece_type" in fields or "kind" in fields:
        item_def.piece_type = piece_type
    if "rarity" in fields:
        item_def.rarity = body.rarity
    if "value" in fields:
        item_def.value = body.value
    if "asset" in fields:
        item_def.asset = asset
    if "is_upgrade_target" in fields:
        item_def.is_upgrade_target = bool(body.is_upgrade_target)
    _audit(
        db, admin, "item_def.patch", f"item_def:{item_def.id}", body.model_dump(mode="json", exclude_unset=True)
    )
    return item_def


async def delete_item_def(db: AsyncSession, admin: User, item_def_id: int) -> None:
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    collection = await db.get(Collection, item_def.collection_id)
    if collection is None or collection.status != "draft":
        raise ITEM_DEF_LOCKED
    await db.execute(delete(CaseDrop).where(CaseDrop.item_def_id == item_def.id))
    await db.delete(item_def)
    _audit(db, admin, "item_def.delete", f"item_def:{item_def_id}", {})


# --- Кейсы -------------------------------------------------------------------


async def create_case(db: AsyncSession, admin: User, collection_id: int, body: CaseCreateIn) -> Case:
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise COLLECTION_NOT_FOUND
    case = Case(
        collection_id=collection.id,
        code=body.code,
        name=body.name,
        price=body.price,
        sort=body.sort,
        is_active=True,
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
    if "is_active" in fields:
        case.is_active = bool(body.is_active)
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
    collection = await db.get(Collection, case.collection_id)
    if collection is None or collection.status != "draft":
        raise CASE_LOCKED
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    await db.delete(case)
    _audit(db, admin, "case.delete", f"case:{case_id}", {})


async def set_drops(
    db: AsyncSession, admin: User, case_id: int, drops: list[DropIn]
) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    collection = await db.get(Collection, case.collection_id)
    if collection is None or collection.status != "draft":
        raise CASE_LOCKED
    allowed_ids = {
        d.id
        for d in (
            await db.scalars(select(ItemDef).where(ItemDef.collection_id == case.collection_id))
        ).all()
    }
    for drop in drops:
        if drop.item_def_id not in allowed_ids:
            raise DROP_ITEM_NOT_IN_COLLECTION
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
    db: AsyncSession, admin: User, case_id: int, kind: str | None
) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    collection = await db.get(Collection, case.collection_id)
    if collection is None or collection.status != "draft":
        raise CASE_LOCKED
    query = select(ItemDef).where(ItemDef.collection_id == case.collection_id)
    if kind is not None:
        query = query.where(ItemDef.kind == kind)
    skins = (await db.scalars(query)).all()
    weights = auto_weights(list(skins), await get_setting(db, "rarity_weights"))
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    for item_def_id, weight in weights.items():
        db.add(CaseDrop(case_id=case.id, item_def_id=item_def_id, weight=weight))
    await db.flush()
    _audit(db, admin, "case.drops.auto", f"case:{case.id}", {"kind": kind})
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
