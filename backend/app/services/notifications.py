from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.clock as clock
from app.core.errors import AppError
from app.models.social import Notification

_NOTIFICATION_NOT_FOUND = AppError(404, "NOTIFICATION_NOT_FOUND", "Уведомление не найдено")
_ALLOWED_KINDS = frozenset({"friend_request", "friend_accepted", "match_invite", "market_sale", "gift"})


async def notify(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: str,
    href: str | None = None,
    now: datetime | None = None,
) -> Notification:
    if kind not in _ALLOWED_KINDS:
        raise AppError(400, "INVALID_NOTIFICATION_KIND", f"Неизвестный тип уведомления: {kind}")
    if href is not None:
        if not href.startswith("/") or href.startswith("//") or "\\" in href:
            raise AppError(400, "INVALID_NOTIFICATION_HREF", "Недопустимый адрес ссылки")
    if now is None:
        now = clock.now()
    notification = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        href=href,
        read=False,
        created_at=now,
    )
    db.add(notification)
    await db.flush()
    return notification


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read.is_(False),
        )
    )
    return count or 0


async def list_notifications(
    db: AsyncSession,
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 20,
) -> tuple[list[Notification], int | None, int]:
    limit = max(1, min(limit, 100))
    query = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(limit + 1)
    )
    if before_id is not None:
        query = query.where(Notification.id < before_id)

    rows = list((await db.scalars(query)).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None
    unread_count = await get_unread_count(db, user_id)
    return items, next_cursor, unread_count


async def mark_read(db: AsyncSession, user_id: int, notification_id: int) -> None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise _NOTIFICATION_NOT_FOUND
    if not notification.read:
        notification.read = True


async def mark_all_read(db: AsyncSession, user_id: int) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read.is_(False))
        .values(read=True)
    )
