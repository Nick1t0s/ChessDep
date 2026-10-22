from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chess_engine import format_chance
from app.core.errors import AppError
from app.models import Collection, InventoryItem, ItemDef, Roll, User
from app.schemas.items import UpgradeOut, UpgradePreviewOut
from app.services.items import create_item, item_out, load_items, lock_items, unequip_items
from app.services.rolls import get_rng, record_roll
from app.services.settings import get_setting

_TOO_MANY_INPUTS = AppError(400, "TOO_MANY_INPUTS", "Слишком много предметов на входе")
_DUPLICATE_INPUTS = AppError(400, "DUPLICATE_INPUTS", "Повторяющиеся предметы на входе")
_TARGET_NOT_AVAILABLE = AppError(400, "UPGRADE_TARGET_NOT_AVAILABLE", "Цель апгрейда недоступна")


async def compute(
    db: AsyncSession, user: User, input_ids: list[int], target_def_id: int, *, lock: bool
) -> tuple[list[InventoryItem], ItemDef, float]:
    max_inputs = int(await get_setting(db, "upgrade_max_inputs"))
    if len(input_ids) > max_inputs:
        raise _TOO_MANY_INPUTS
    if len(set(input_ids)) != len(input_ids):
        raise _DUPLICATE_INPUTS
    fetcher = lock_items if lock else load_items
    items = await fetcher(db, user.id, input_ids)
    target = await db.get(ItemDef, target_def_id)
    if target is None:
        raise _TARGET_NOT_AVAILABLE
    collection = await db.get(Collection, target.collection_id)
    if collection is None or collection.status != "released" or not target.is_upgrade_target:
        raise _TARGET_NOT_AVAILABLE
    edge = float(await get_setting(db, "upgrade_edge"))
    min_chance = float(await get_setting(db, "upgrade_min_chance"))
    max_chance = float(await get_setting(db, "upgrade_max_chance"))
    def_ids = {item.item_def_id for item in items}
    defs = {
        d.id: d
        for d in (await db.scalars(select(ItemDef).where(ItemDef.id.in_(def_ids)))).all()
    }
    input_value = sum(defs[item.item_def_id].value for item in items)
    chance = input_value / target.value * (1.0 - edge)
    if chance < min_chance or chance > max_chance:
        # Новый экземпляр: к исключению прикрепляется посчитанный шанс
        # (preview покажет его с allowed=False).
        error = AppError(
            400, "UPGRADE_CHANCE_OUT_OF_RANGE", "Шанс апгрейда вне допустимого диапазона"
        )
        error.chance = chance  # type: ignore[attr-defined]
        raise error
    return items, target, chance


async def preview(
    db: AsyncSession, user: User, input_ids: list[int], target_def_id: int
) -> UpgradePreviewOut:
    try:
        _, _, chance = await compute(db, user, input_ids, target_def_id, lock=False)
    except AppError as exc:
        if exc.code == "ITEM_NOT_OWNED":
            raise
        chance_attr = getattr(exc, "chance", 0.0)
        chance = float(chance_attr) if chance_attr is not None else 0.0
        return UpgradePreviewOut(
            chance=chance, chance_text=format_chance(chance), allowed=False, reason=exc.code
        )
    return UpgradePreviewOut(
        chance=chance, chance_text=format_chance(chance), allowed=True, reason=None
    )


async def execute(
    db: AsyncSession, user: User, input_ids: list[int], target_def_id: int, now: datetime
) -> UpgradeOut:
    items, target, chance = await compute(db, user, input_ids, target_def_id, lock=True)
    def_ids = {item.item_def_id for item in items}
    defs = {
        d.id: d
        for d in (await db.scalars(select(ItemDef).where(ItemDef.id.in_(def_ids)))).all()
    }
    input_value = sum(defs[item.item_def_id].value for item in items)
    burned_ids = sorted(item.id for item in items)

    # Порядок блокировок: предметы по возрастанию id (в bench… compute lock_items);
    # баланс не меняется.
    rng = get_rng()
    r = rng.random()
    success = r < chance

    await unequip_items(db, burned_ids)
    for item in items:
        item.status = "burned"
        item.burned_at = now

    roll_id = await record_roll(
        db,
        user_id=user.id,
        kind="upgrade",
        ref=str(target.id),
        chance=chance,
        roll_value=r,
        input={"input_ids": burned_ids, "input_value": input_value, "target_def_id": target.id},
        outcome={"success": success, "item_id": None},
    )
    item = None
    if success:
        # wear расходует следующий rng.random().
        item = await create_item(
            db,
            user_id=user.id,
            def_id=target.id,
            source="upgrade",
            source_ref=str(roll_id),
            now=now,
        )
        roll = await db.get(Roll, roll_id)
        # Новый dict целиком, чтобы SQLAlchemy увидел изменение JSONB.
        roll.outcome = {"success": True, "item_id": item.id}
    return UpgradeOut(
        success=success,
        chance=chance,
        chance_text=format_chance(chance),
        roll_value=r,
        roll_id=roll_id,
        burned_ids=burned_ids,
        item=await item_out(db, item) if item is not None else None,
    )
