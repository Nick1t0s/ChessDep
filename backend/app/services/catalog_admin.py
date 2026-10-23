from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    AdminAudit,
    Case,
    CaseDrop,
    Collection,
    DailyRewardPool,
    ItemDef,
    ItemSet,
    User,
)
from app.schemas.items import (
    BoardCreateIn,
    CaseCreateIn,
    CasePatchIn,
    CollectionCreateIn,
    CollectionPatchIn,
    DailyPoolEntryIn,
    DropIn,
    ItemDefPatchIn,
    SetCreateIn,
    SetPatchIn,
)
from app.seed_data import item_code, item_name
from app.services.cases import auto_weights
from app.services.items import create_case_item, create_item
from app.services.settings import get_setting
from app.services.skin_images import ensure_image

SET_NOT_FOUND = AppError(404, "SET_NOT_FOUND", "Набор не найден")
COLLECTION_NOT_FOUND = AppError(404, "COLLECTION_NOT_FOUND", "Коллекция не найдена")
ITEM_DEF_NOT_FOUND = AppError(404, "ITEM_DEF_NOT_FOUND", "Скин не найден")
CASE_NOT_FOUND = AppError(404, "CASE_NOT_FOUND", "Кейс не найден")
USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")

SET_CODE_TAKEN = AppError(409, "SET_CODE_TAKEN", "Код набора занят")
COLLECTION_CODE_TAKEN = AppError(409, "COLLECTION_CODE_TAKEN", "Код коллекции занят")
ITEM_CODE_TAKEN = AppError(409, "ITEM_CODE_TAKEN", "Код скина занят")
CASE_CODE_TAKEN = AppError(409, "CASE_CODE_TAKEN", "Код кейса занят")

SET_NOT_DRAFT = AppError(400, "SET_NOT_DRAFT", "Действие только для черновика")
SET_NOT_RELEASED = AppError(400, "SET_NOT_RELEASED", "Снять можно только выпущенный")
SET_EMPTY = AppError(400, "SET_EMPTY", "В наборе нет коллекций и досок")
SET_IS_BASE = AppError(400, "SET_IS_BASE", "Базовый набор нельзя менять")

ITEM_DEF_LOCKED = AppError(
    400, "ITEM_DEF_LOCKED", "После выпуска можно менять только name, asset, value, is_upgrade_target"
)
ITEM_DEF_NOT_AVAILABLE = AppError(
    400, "ITEM_DEF_NOT_AVAILABLE", "Скин или кейс недоступен для выдачи"
)
ASSET_REQUIRED = AppError(422, "VALIDATION_ERROR", "asset не может быть пустым")

CASE_LOCKED = AppError(400, "CASE_LOCKED", "Дропы можно менять только у черновика кейса")
CASE_NOT_READY = AppError(
    400, "CASE_NOT_READY", "Кейс не готов: нет дропов, есть невыпущенные наборы или тираж исчерпан"
)
CASE_NOT_ON_SALE = AppError(400, "CASE_NOT_ON_SALE", "Кейс не в продаже")
CASE_NOT_AVAILABLE = AppError(400, "CASE_NOT_AVAILABLE", "Кейс недоступен")
DROP_ITEM_NOT_AVAILABLE = AppError(400, "DROP_ITEM_NOT_AVAILABLE", "Скин недоступен для кейса")

STOCK_BELOW_SOLD = AppError(422, "VALIDATION_ERROR", "Тираж меньше уже проданного")
SALE_WINDOW_INVALID = AppError(422, "VALIDATION_ERROR", "Начало продаж должно быть раньше конца")


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


# --- Наборы ------------------------------------------------------------------


async def create_set(
    db: AsyncSession, admin: User, body: SetCreateIn
) -> ItemSet:
    item_set = ItemSet(
        code=body.code,
        name=body.name,
        description=body.description,
        status="draft",
        is_base=False,
    )
    db.add(item_set)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise SET_CODE_TAKEN from exc
    _audit(db, admin, "set.create", f"set:{item_set.id}", body.model_dump(mode="json"))
    return item_set


async def patch_set(
    db: AsyncSession, admin: User, set_id: int, body: SetPatchIn
) -> ItemSet:
    item_set = await db.get(ItemSet, set_id)
    if item_set is None:
        raise SET_NOT_FOUND
    fields = body.model_fields_set
    if "name" in fields:
        item_set.name = body.name
    if "description" in fields:
        item_set.description = body.description
    _audit(
        db,
        admin,
        "set.patch",
        f"set:{item_set.id}",
        body.model_dump(mode="json", exclude_unset=True),
    )
    return item_set


async def delete_set(db: AsyncSession, admin: User, set_id: int) -> None:
    item_set = await db.get(ItemSet, set_id)
    if item_set is None:
        raise SET_NOT_FOUND
    if item_set.is_base:
        raise SET_IS_BASE
    if item_set.status != "draft":
        raise SET_NOT_DRAFT
    collection_ids = select(Collection.id).where(Collection.set_id == set_id)
    case_ids = select(Case.id).where(
        or_(Case.set_id == set_id, Case.collection_id.in_(collection_ids))
    )
    await db.execute(delete(DailyRewardPool).where(DailyRewardPool.case_id.in_(case_ids)))
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id.in_(case_ids)))
    await db.execute(delete(Case).where(Case.id.in_(case_ids)))
    def_ids = select(ItemDef.id).where(ItemDef.set_id == set_id)
    await db.execute(delete(CaseDrop).where(CaseDrop.item_def_id.in_(def_ids)))
    await db.execute(delete(ItemDef).where(ItemDef.set_id == set_id))
    await db.execute(delete(Collection).where(Collection.set_id == set_id))
    await db.delete(item_set)
    _audit(db, admin, "set.delete", f"set:{set_id}", {})


async def release_set(
    db: AsyncSession, admin: User, set_id: int, now: datetime
) -> ItemSet:
    item_set = await db.get(ItemSet, set_id)
    if item_set is None:
        raise SET_NOT_FOUND
    if item_set.is_base:
        raise SET_IS_BASE
    if item_set.status != "draft":
        raise SET_NOT_DRAFT
    collections_count = await db.scalar(
        select(func.count()).select_from(Collection).where(Collection.set_id == set_id)
    )
    boards_count = await db.scalar(
        select(func.count())
        .select_from(ItemDef)
        .where(ItemDef.set_id == set_id, ItemDef.kind == "board")
    )
    if not collections_count and not boards_count:
        raise SET_EMPTY
    item_set.status = "released"
    item_set.released_at = now
    _audit(db, admin, "set.release", f"set:{item_set.id}", {})
    return item_set


async def retire_set(
    db: AsyncSession, admin: User, set_id: int, now: datetime
) -> ItemSet:
    item_set = await db.get(ItemSet, set_id)
    if item_set is None:
        raise SET_NOT_FOUND
    if item_set.is_base:
        raise SET_IS_BASE
    if item_set.status != "released":
        raise SET_NOT_RELEASED
    ids = list(
        (
            await db.scalars(
                select(Case.id)
                .join(CaseDrop, CaseDrop.case_id == Case.id)
                .join(ItemDef, ItemDef.id == CaseDrop.item_def_id)
                .where(ItemDef.set_id == item_set.id, Case.status == "on_sale")
                .distinct()
                .order_by(Case.id)
            )
        ).all()
    )
    if ids:
        await db.execute(update(Case).where(Case.id.in_(ids)).values(status="off_sale"))
    item_set.status = "retired"
    item_set.retired_at = now
    _audit(
        db, admin, "set.retire", f"set:{item_set.id}", {"unpublished_case_ids": ids}
    )
    return item_set


async def _draft_set(db: AsyncSession, set_id: int) -> ItemSet:
    item_set = await db.get(ItemSet, set_id)
    if item_set is None:
        raise SET_NOT_FOUND
    if item_set.status != "draft":
        raise SET_NOT_DRAFT
    return item_set


# --- Коллекции и скины -------------------------------------------------------


async def create_collection(
    db: AsyncSession, admin: User, set_id: int, body: CollectionCreateIn
) -> Collection:
    await _draft_set(db, set_id)
    for p in body.pieces:
        await ensure_image(db, p.asset.image, "piece")
    collection = Collection(
        set_id=set_id,
        code=body.code,
        name=body.name,
        description=body.description,
    )
    db.add(collection)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise COLLECTION_CODE_TAKEN from exc

    for p in body.pieces:
        db.add(
            ItemDef(
                kind="piece",
                set_id=set_id,
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

    _audit(
        db, admin, "collection.create", f"collection:{collection.id}", body.model_dump(mode="json")
    )
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
    item_set = await db.get(ItemSet, collection.set_id)
    if item_set is None or item_set.status != "draft":
        raise SET_NOT_DRAFT
    def_ids = select(ItemDef.id).where(ItemDef.collection_id == collection.id)
    await db.execute(delete(CaseDrop).where(CaseDrop.item_def_id.in_(def_ids)))
    await db.execute(delete(ItemDef).where(ItemDef.collection_id == collection.id))
    await db.delete(collection)
    _audit(db, admin, "collection.delete", f"collection:{collection_id}", {})


async def create_board(
    db: AsyncSession, admin: User, set_id: int, body: BoardCreateIn
) -> ItemDef:
    await _draft_set(db, set_id)
    await ensure_image(db, body.asset.image, "board")
    item_def = ItemDef(
        kind="board",
        set_id=set_id,
        collection_id=None,
        side=None,
        piece_type=None,
        code=body.code,
        name=body.name,
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
    _audit(db, admin, "board.create", f"item_def:{item_def.id}", body.model_dump(mode="json"))
    return item_def


async def patch_item_def(
    db: AsyncSession, admin: User, item_def_id: int, body: ItemDefPatchIn
) -> ItemDef:
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    item_set = await db.get(ItemSet, item_def.set_id)
    fields = body.model_fields_set
    if "rarity" in fields and (item_set is None or item_set.status != "draft"):
        raise ITEM_DEF_LOCKED
    if "asset" in fields:
        if body.asset is None:
            raise ASSET_REQUIRED
        await ensure_image(db, body.asset.image, item_def.kind)
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


async def delete_item_def(db: AsyncSession, admin: User, item_def_id: int) -> None:
    item_def = await db.get(ItemDef, item_def_id)
    if item_def is None:
        raise ITEM_DEF_NOT_FOUND
    item_set = await db.get(ItemSet, item_def.set_id)
    if item_def.kind == "piece" or item_set is None or item_set.status != "draft":
        raise ITEM_DEF_LOCKED
    await db.execute(delete(CaseDrop).where(CaseDrop.item_def_id == item_def.id))
    await db.delete(item_def)
    _audit(db, admin, "item_def.delete", f"item_def:{item_def.id}", {})


# --- Кейсы -------------------------------------------------------------------


async def create_case(db: AsyncSession, admin: User, body: CaseCreateIn) -> Case:
    if body.kind == "set":
        item_set = await db.get(ItemSet, body.set_id)
        if item_set is None:
            raise SET_NOT_FOUND
        if item_set.is_base:
            raise SET_IS_BASE
    elif body.kind == "collection":
        collection = await db.get(Collection, body.collection_id)
        if collection is None:
            raise COLLECTION_NOT_FOUND
        item_set = await db.get(ItemSet, collection.set_id)
        if item_set is None or item_set.is_base:
            raise SET_IS_BASE
    case = Case(
        code=body.code,
        name=body.name,
        kind=body.kind,
        set_id=body.set_id,
        collection_id=body.collection_id,
        price=body.price,
        sort=body.sort,
        stock_limit=body.stock_limit,
        sale_starts_at=body.sale_starts_at,
        sale_ends_at=body.sale_ends_at,
        status="draft",
        sold_count=0,
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
    stock_limit = body.stock_limit if "stock_limit" in fields else case.stock_limit
    if stock_limit is not None and stock_limit < case.sold_count:
        raise STOCK_BELOW_SOLD
    starts = body.sale_starts_at if "sale_starts_at" in fields else case.sale_starts_at
    ends = body.sale_ends_at if "sale_ends_at" in fields else case.sale_ends_at
    if starts is not None and ends is not None and starts >= ends:
        raise SALE_WINDOW_INVALID
    if "name" in fields:
        case.name = body.name
    if "price" in fields:
        case.price = body.price
    if "sort" in fields:
        case.sort = body.sort
    if "stock_limit" in fields:
        case.stock_limit = body.stock_limit
    if "sale_starts_at" in fields:
        case.sale_starts_at = body.sale_starts_at
    if "sale_ends_at" in fields:
        case.sale_ends_at = body.sale_ends_at
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
    await db.execute(delete(DailyRewardPool).where(DailyRewardPool.case_id == case.id))
    await db.delete(case)
    _audit(db, admin, "case.delete", f"case:{case_id}", {})


async def _draft_case(db: AsyncSession, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status != "draft":
        raise CASE_LOCKED
    return case


async def _allowed_def_ids(db: AsyncSession, case: Case) -> set[int]:
    query = (
        select(ItemDef.id)
        .join(ItemSet, ItemSet.id == ItemDef.set_id)
        .where(ItemSet.is_base.is_(False), ItemSet.status != "retired")
    )
    if case.kind == "set":
        query = query.where(ItemDef.set_id == case.set_id)
    elif case.kind == "collection":
        query = query.where(ItemDef.collection_id == case.collection_id)
    return set((await db.scalars(query)).all())


async def set_drops(
    db: AsyncSession, admin: User, case_id: int, drops: list[DropIn]
) -> Case:
    case = await _draft_case(db, case_id)
    allowed = await _allowed_def_ids(db, case)
    if any(d.item_def_id not in allowed for d in drops):
        raise DROP_ITEM_NOT_AVAILABLE
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
    db: AsyncSession,
    admin: User,
    case_id: int,
    set_ids: list[int],
    collection_ids: list[int],
) -> Case:
    case = await _draft_case(db, case_id)
    if case.kind == "set":
        skins = list(
            (await db.scalars(select(ItemDef).where(ItemDef.set_id == case.set_id))).all()
        )
    elif case.kind == "collection":
        skins = list(
            (
                await db.scalars(
                    select(ItemDef).where(ItemDef.collection_id == case.collection_id)
                )
            ).all()
        )
    else:
        if not set_ids and not collection_ids:
            raise AppError(422, "VALIDATION_ERROR", "Укажите наборы или коллекции")
        sets_by_id: dict[int, ItemSet] = {}
        if set_ids:
            sets_by_id = {
                s.id: s
                for s in (await db.scalars(select(ItemSet).where(ItemSet.id.in_(set_ids)))).all()
            }
            for sid in set_ids:
                item_set = sets_by_id.get(sid)
                if item_set is None:
                    raise SET_NOT_FOUND
                if item_set.is_base:
                    raise SET_IS_BASE
                if item_set.status == "retired":
                    raise DROP_ITEM_NOT_AVAILABLE
        collections_by_id: dict[int, Collection] = {}
        if collection_ids:
            collections_by_id = {
                c.id: c
                for c in (
                    await db.scalars(
                        select(Collection).where(Collection.id.in_(collection_ids))
                    )
                ).all()
            }
            for cid in collection_ids:
                collection = collections_by_id.get(cid)
                if collection is None:
                    raise COLLECTION_NOT_FOUND
            parent_set_ids = {collections_by_id[cid].set_id for cid in collection_ids}
            parent_sets = {
                s.id: s
                for s in (
                    await db.scalars(select(ItemSet).where(ItemSet.id.in_(parent_set_ids)))
                ).all()
            }
            for cid in collection_ids:
                parent = parent_sets[collections_by_id[cid].set_id]
                if parent is None:
                    raise SET_NOT_FOUND
                if parent.is_base:
                    raise SET_IS_BASE
                if parent.status == "retired":
                    raise DROP_ITEM_NOT_AVAILABLE
        conditions = []
        if set_ids:
            conditions.append(ItemDef.set_id.in_(set_ids))
        if collection_ids:
            conditions.append(ItemDef.collection_id.in_(collection_ids))
        skins = list(
            (await db.scalars(select(ItemDef).where(or_(*conditions)))).all()
        )
    weights = auto_weights(skins, await get_setting(db, "rarity_weights"))
    await db.execute(delete(CaseDrop).where(CaseDrop.case_id == case.id))
    for item_def_id, weight in weights.items():
        db.add(CaseDrop(case_id=case.id, item_def_id=item_def_id, weight=weight))
    await db.flush()
    _audit(
        db,
        admin,
        "case.drops.auto",
        f"case:{case.id}",
        {"set_ids": set_ids, "collection_ids": collection_ids},
    )
    return case


async def publish_case(db: AsyncSession, admin: User, case_id: int, now: datetime) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status == "on_sale":
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
        .join(ItemSet, ItemSet.id == ItemDef.set_id)
        .where(CaseDrop.case_id == case.id, ItemSet.status != "released")
    )
    if (not_released_count or 0) > 0:
        raise CASE_NOT_READY
    if case.stock_limit is not None and case.sold_count >= case.stock_limit:
        raise CASE_NOT_READY
    case.status = "on_sale"
    _audit(db, admin, "case.publish", f"case:{case.id}", {})
    return case


async def unpublish_case(db: AsyncSession, admin: User, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise CASE_NOT_FOUND
    if case.status != "on_sale":
        raise CASE_NOT_ON_SALE
    case.status = "off_sale"
    _audit(db, admin, "case.unpublish", f"case:{case.id}", {})
    return case


# --- Пул и выдача ------------------------------------------------------------


async def set_daily_pool(
    db: AsyncSession, admin: User, entries: list[DailyPoolEntryIn]
) -> None:
    for entry in entries:
        case = await db.get(Case, entry.case_id)
        if case is None or case.status == "draft":
            raise CASE_NOT_AVAILABLE
    await db.execute(delete(DailyRewardPool))
    for entry in entries:
        db.add(DailyRewardPool(case_id=entry.case_id, weight=entry.weight))
    await db.flush()
    _audit(
        db,
        admin,
        "daily_pool.set",
        "daily_reward_pool",
        {"entries": [[entry.case_id, entry.weight] for entry in entries]},
    )


async def grant_item(
    db: AsyncSession,
    admin: User,
    user_id: int,
    item_def_id: int | None,
    case_id: int | None,
    now: datetime,
) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    if item_def_id is not None:
        item_def = await db.get(ItemDef, item_def_id)
        if item_def is None:
            raise ITEM_DEF_NOT_FOUND
        item_set = await db.get(ItemSet, item_def.set_id)
        if item_set is None or item_set.is_base or item_set.status != "released":
            raise ITEM_DEF_NOT_AVAILABLE
        item = await create_item(
            db,
            user_id=user.id,
            def_id=item_def.id,
            source="admin_grant",
            source_ref=str(admin.id),
            now=now,
        )
    else:
        case = await db.get(Case, case_id)
        if case is None:
            raise CASE_NOT_FOUND
        if case.status == "draft":
            raise ITEM_DEF_NOT_AVAILABLE
        item = await create_case_item(
            db,
            user_id=user.id,
            case_id=case.id,
            source="admin_grant",
            source_ref=str(admin.id),
            now=now,
        )
    _audit(
        db,
        admin,
        "user.grant_item",
        f"user:{user.id}",
        {"item_def_id": item_def_id, "case_id": case_id},
    )
    return item.id
