from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import InventoryItem, ItemTransfer, User
from app.schemas.gifts import GiftOut, GiftsPage
from app.schemas.market import ListingItemOut
from app.services.items import check_trade_hold, items_out, lock_items, unequip_items
from app.services.settings import get_setting

_USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
_CANNOT_GIFT_SELF = AppError(400, "CANNOT_GIFT_SELF", "Нельзя подарить себе")
_RECIPIENT_BANNED = AppError(400, "RECIPIENT_BANNED", "Получатель заблокирован")


async def send_gift(
    db: AsyncSession, sender: User, item_id: int, to_login: str, note: str | None, now
) -> ItemTransfer:
    recipient = await db.scalar(select(User).where(User.login == to_login))
    if recipient is None:
        raise _USER_NOT_FOUND
    if recipient.id == sender.id:
        raise _CANNOT_GIFT_SELF
    if recipient.is_banned:
        raise _RECIPIENT_BANNED
    items = await lock_items(db, sender.id, [item_id])
    item = items[0]
    hold = int(await get_setting(db, "trade_hold_hours"))
    check_trade_hold(item, hold, now)
    await unequip_items(db, [item.id])
    item.user_id = recipient.id
    item.acquired_at = now
    transfer = ItemTransfer(
        item_id=item.id,
        from_user_id=sender.id,
        to_user_id=recipient.id,
        kind="gift",
        ref=None,
        note=note,
        seen=False,
        created_at=now,
    )
    db.add(transfer)
    await db.flush()
    return transfer


async def _items_for(db: AsyncSession, rows: list[ItemTransfer]) -> list[InventoryItem]:
    item_ids = [transfer.item_id for transfer in rows]
    if not item_ids:
        return []
    found = {
        item.id: item
        for item in (
            await db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))
        ).all()
    }
    return [found[transfer.item_id] for transfer in rows]


def _item_brief(item_out) -> ListingItemOut:
    return ListingItemOut(
        id=item_out.id,
        item_def=item_out.item_def,
        wear=item_out.wear,
        exterior=item_out.exterior,
    )


async def list_gifts(
    db: AsyncSession, user: User, direction: str, before_id: int | None, limit: int
) -> GiftsPage:
    if direction == "in":
        filter_user = ItemTransfer.to_user_id == user.id
    else:
        filter_user = ItemTransfer.from_user_id == user.id
    query = select(ItemTransfer).where(filter_user, ItemTransfer.kind == "gift")
    if before_id is not None:
        query = query.where(ItemTransfer.id < before_id)
    rows = list(
        (await db.scalars(query.order_by(ItemTransfer.id.desc()).limit(limit))).all()
    )

    user_ids = set()
    for transfer in rows:
        user_ids.add(transfer.from_user_id)
        user_ids.add(transfer.to_user_id)
    logins: dict[int, str] = {}
    if user_ids:
        for row in (
            await db.execute(select(User.id, User.login).where(User.id.in_(user_ids)))
        ).all():
            logins[row[0]] = row[1]
    item_outs = await items_out(db, await _items_for(db, rows))
    result: list[GiftOut] = []
    for index, transfer in enumerate(rows):
        result.append(
            GiftOut(
                id=transfer.id,
                item=_item_brief(item_outs[index]),
                from_login=logins[transfer.from_user_id],
                to_login=logins[transfer.to_user_id],
                note=transfer.note,
                seen=transfer.seen,
                created_at=transfer.created_at,
            )
        )
    if direction == "in":
        # seen в ответе — значение до пометки; помечаем все входящие целиком.
        await db.execute(
            update(ItemTransfer)
            .where(
                ItemTransfer.to_user_id == user.id,
                ItemTransfer.kind == "gift",
                ItemTransfer.seen.is_(False),
            )
            .values(seen=True)
        )
    next_cursor = result[-1].id if len(result) == limit else None
    return GiftsPage(items=result, next_cursor=next_cursor)


async def unseen_count(db: AsyncSession, user: User) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(ItemTransfer)
            .where(
                ItemTransfer.to_user_id == user.id,
                ItemTransfer.kind == "gift",
                ItemTransfer.seen.is_(False),
            )
        )
    )
