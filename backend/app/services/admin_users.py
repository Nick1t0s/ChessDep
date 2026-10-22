from datetime import datetime
from typing import Any

import app.core.clock as clock
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.sessions import revoke_all
from app.db import after_commit
from app.models import (
    ActivePlayer,
    AdminAudit,
    MarketListing,
    Setting,
    User,
)
from app.services import games as games_service
from app.services import market as market_service
from app.services import matchmaking
from app.services.economy import apply_delta, lock_user
from app.services.settings import DEFAULTS, SETTINGS_SCHEMA, clear_cache

_USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
_CANNOT_BAN_SELF = AppError(400, "CANNOT_BAN_SELF", "Нельзя забанить себя")
_CANNOT_BAN_ADMIN = AppError(
    400, "CANNOT_BAN_ADMIN", "Нельзя забанить админа: сначала снимите роль через CLI"
)
_SETTINGS_INCONSISTENT = AppError(
    400, "SETTINGS_INCONSISTENT", "Настройки противоречат друг другу"
)
_SETTING_NOT_FOUND = AppError(404, "SETTING_NOT_FOUND", "Неизвестная настройка")
_VALIDATION_ERROR = AppError(422, "VALIDATION_ERROR", "Некорректные данные")


def audit(db: AsyncSession, admin: User, action: str, target: str, payload: Any) -> None:
    db.add(
        AdminAudit(
            admin_id=admin.id,
            action=action,
            target=target,
            payload=payload,
        )
    )


async def get_setting_current(db: AsyncSession, key: str) -> Any:
    row = await db.get(Setting, key)
    return row.value if row is not None else DEFAULTS[key]


async def ban_user(db: AsyncSession, admin: User, user_id: int, reason: str, now: datetime) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    if user.id == admin.id:
        raise _CANNOT_BAN_SELF
    if user.role == "admin":
        raise _CANNOT_BAN_ADMIN
    if user.is_banned:
        return user

    # 2. Активные лоты по возрастанию id: лот → предмет на каждый.
    listing_ids = list(
        (
            await db.scalars(
                select(MarketListing.id)
                .where(MarketListing.seller_id == user_id, MarketListing.status == "active")
                .order_by(MarketListing.id)
            )
        ).all()
    )
    for listing_id in listing_ids:
        await market_service.cancel_listing(db, user, listing_id, now, by_admin=admin)

    # 3. Активная партия: games затем пользователи внутри forfeit/finish_game.
    game_id = await db.scalar(select(ActivePlayer.game_id).where(ActivePlayer.user_id == user_id))
    if game_id is not None:
        game = await games_service.lock_game(db, game_id)
        color = games_service.color_of(game, user_id)
        await games_service.forfeit(db, game, color, now)

    # 4. Пользователь (users — последняя сущность по порядку блокировок).
    banned = await lock_user(db, user_id)
    banned.is_banned = True
    await revoke_all(db, user_id)

    # 5. Очередь матчмейкинга — только после коммита (Redis).
    async def _dequeue() -> None:
        await matchmaking.dequeue(banned)

    after_commit(db, _dequeue)

    # 6. Аудит.
    audit(db, admin, "user.ban", f"user:{user_id}", {"reason": reason})
    return banned


async def unban_user(db: AsyncSession, admin: User, user_id: int, now: datetime) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    banned = await lock_user(db, user_id)
    banned.is_banned = False
    audit(db, admin, "user.unban", f"user:{user_id}", {})
    return banned


async def adjust_balance(
    db: AsyncSession, admin: User, user_id: int, delta: int, comment: str
) -> int:
    user = await db.get(User, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    new_balance = await apply_delta(
        db, user_id, delta, "admin_adjust", ref=comment, actor_id=admin.id
    )
    audit(db, admin, "user.balance", f"user:{user_id}", {"delta": delta, "comment": comment})
    return new_balance


async def set_setting(db: AsyncSession, admin: User, key: str, value: Any, now: datetime) -> Any:
    if key not in DEFAULTS:
        raise _SETTING_NOT_FOUND
    validator = SETTINGS_SCHEMA[key]
    try:
        normalized = validator(value)
    except ValidationError:
        raise _VALIDATION_ERROR

    # Перекрёстная проверка min/max шансов апгрейда против текущего значения второго ключа.
    if key == "upgrade_min_chance":
        if float(normalized) > float(await get_setting_current(db, "upgrade_max_chance")):
            raise _SETTINGS_INCONSISTENT
    elif key == "upgrade_max_chance":
        if float(normalized) < float(await get_setting_current(db, "upgrade_min_chance")):
            raise _SETTINGS_INCONSISTENT

    await db.execute(
        insert(Setting)
        .values(key=key, value=normalized, updated_at=now, updated_by=admin.id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={
                "value": normalized,
                "updated_at": now,
                "updated_by": admin.id,
            },
        )
    )
    clear_cache()
    audit(db, admin, "settings.update", f"settings:{key}", {"value": normalized})
    return normalized


async def cancel_listing_by_admin(
    db: AsyncSession, admin: User, listing_id: int, reason: str
) -> MarketListing:
    listing = await market_service.cancel_listing(
        db, admin, listing_id, clock.now(), by_admin=admin
    )
    audit(db, admin, "market.cancel", f"listing:{listing_id}", {"reason": reason})
    return listing
