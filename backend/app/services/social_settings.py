from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.game import ActivePlayer, Game
from app.models.social import Friendship, UserBlock, UserSocialSettings
from app.models.user import User
from app.redis import redis_client
from app.schemas.social import DEFAULT_NOTIFICATION_SETTINGS

_CONTACT_BLOCKED = AppError(403, "CONTACT_BLOCKED", "Пользователь заблокирован")
_CANNOT_BLOCK_SELF = AppError(400, "CANNOT_BLOCK_SELF", "Нельзя заблокировать себя")
_USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
_USER_BANNED = AppError(403, "USER_BANNED", "Пользователь заблокирован")
_CANNOT_INVITE_SELF = AppError(400, "CANNOT_INVITE_SELF", "Нельзя пригласить себя")
_FRIEND_REQUIRED = AppError(403, "FRIEND_REQUIRED", "Приглашение доступно только друзьям")
_INVITES_DISABLED = AppError(403, "INVITES_DISABLED", "Пользователь не принимает приглашения")


async def get_or_create_social_settings(db: AsyncSession, user_id: int) -> UserSocialSettings:
    """Возвращает настройки пользователя, создавая строку по умолчанию concurrency-safe."""
    stmt = (
        pg_insert(UserSocialSettings)
        .values(
            user_id=user_id,
            presence_mode="online",
            match_invites="all",
            notification_settings={},
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    await db.execute(stmt)
    settings = await db.get(UserSocialSettings, user_id)
    if settings is None:
        settings = await db.scalar(
            select(UserSocialSettings).where(UserSocialSettings.user_id == user_id)
        )
    if settings is None:
        raise _USER_NOT_FOUND
    return settings


async def get_social_settings(db: AsyncSession, user_id: int) -> dict[str, Any]:
    settings = await get_or_create_social_settings(db, user_id)
    merged_notifications = dict(DEFAULT_NOTIFICATION_SETTINGS)
    if settings.notification_settings:
        merged_notifications.update(settings.notification_settings)
    return {
        "presence_mode": settings.presence_mode,
        "match_invites": settings.match_invites,
        "notifications": merged_notifications,
    }


async def update_social_settings(
    db: AsyncSession,
    user_id: int,
    *,
    presence_mode: str | None = None,
    match_invites: str | None = None,
    notifications: dict[str, bool] | None = None,
) -> dict[str, Any]:
    await get_or_create_social_settings(db, user_id)

    settings = await db.scalar(
        select(UserSocialSettings)
        .where(UserSocialSettings.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if settings is None:
        raise _USER_NOT_FOUND

    if presence_mode is not None:
        settings.presence_mode = presence_mode
    if match_invites is not None:
        settings.match_invites = match_invites
    if notifications is not None:
        current_map = dict(settings.notification_settings or {})
        current_map.update(notifications)
        settings.notification_settings = current_map
    await db.flush()

    merged_notifications = dict(DEFAULT_NOTIFICATION_SETTINGS)
    if settings.notification_settings:
        merged_notifications.update(settings.notification_settings)
    return {
        "presence_mode": settings.presence_mode,
        "match_invites": settings.match_invites,
        "notifications": merged_notifications,
    }


async def record_presence_heartbeat(
    db: AsyncSession,
    user_id: int,
    presence_mode: str | None = None,
) -> str:
    """Обновляет heartbeat в Redis на 70 секунд и возвращает эффективный presence_mode."""
    await redis_client.set(f"presence:{user_id}", "1", ex=70)
    settings = await get_or_create_social_settings(db, user_id)
    if presence_mode is not None and presence_mode != settings.presence_mode:
        settings.presence_mode = presence_mode
        await db.flush()
    return settings.presence_mode


async def check_user_heartbeat(user_id: int) -> bool:
    val = await redis_client.get(f"presence:{user_id}")
    return val is not None


async def batch_get_presence(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, tuple[str, str | None]]:
    if not user_ids:
        return {}

    keys = [f"presence:{uid}" for uid in user_ids]
    heartbeats = await redis_client.mget(*keys)
    hb_map = {uid: (hb is not None) for uid, hb in zip(user_ids, heartbeats)}

    settings_rows = (
        await db.scalars(
            select(UserSocialSettings).where(UserSocialSettings.user_id.in_(user_ids))
        )
    ).all()
    mode_map = {s.user_id: s.presence_mode for s in settings_rows}

    # Проверяем активные игры через ActivePlayer + Game.status == 'active'
    active_rows = (
        await db.execute(
            select(ActivePlayer.user_id, ActivePlayer.game_id)
            .join(Game, Game.id == ActivePlayer.game_id)
            .where(ActivePlayer.user_id.in_(user_ids), Game.status == "active")
        )
    ).all()
    active_game_map = {row[0]: str(row[1]) for row in active_rows}

    result: dict[int, tuple[str, str | None]] = {}
    for uid in user_ids:
        has_hb = hb_map.get(uid, False)
        mode = mode_map.get(uid, "online")
        active_gid = active_game_map.get(uid)

        # DND при активной игре сохраняет game_id, чтобы зрители могли смотреть партию
        if has_hb and mode == "dnd":
            result[uid] = ("dnd", active_gid)
        elif active_gid is not None:
            result[uid] = ("in_game", active_gid)
        elif has_hb:
            result[uid] = ("online", None)
        else:
            result[uid] = ("offline", None)
    return result


async def get_user_presence_and_game(
    db: AsyncSession, user_id: int
) -> tuple[str, str | None]:
    res = await batch_get_presence(db, [user_id])
    return res.get(user_id, ("offline", None))


async def ensure_not_blocked(db: AsyncSession, user_id: int, other_id: int) -> None:
    """Бросает 403 CONTACT_BLOCKED если есть блокировка в любую из сторон."""
    if user_id == other_id:
        return
    blocked = await db.scalar(
        select(UserBlock.id).where(
            or_(
                and_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == other_id),
                and_(UserBlock.blocker_id == other_id, UserBlock.blocked_id == user_id),
            )
        ).limit(1)
    )
    if blocked is not None:
        raise _CONTACT_BLOCKED


async def ensure_invitation_allowed(
    db: AsyncSession,
    sender_id: int,
    recipient_id: int,
    *,
    require_friendship: bool = False,
) -> User:
    if sender_id == recipient_id:
        raise _CANNOT_INVITE_SELF

    recipient = await db.get(User, recipient_id)
    if recipient is None:
        raise _USER_NOT_FOUND
    if recipient.is_banned:
        raise _USER_BANNED

    await ensure_not_blocked(db, sender_id, recipient_id)

    low_id, high_id = (sender_id, recipient_id) if sender_id < recipient_id else (recipient_id, sender_id)
    friendship = await db.scalar(
        select(Friendship).where(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
            Friendship.status == "accepted",
        )
    )
    is_friends = friendship is not None
    if require_friendship and not is_friends:
        raise _FRIEND_REQUIRED

    settings = await get_or_create_social_settings(db, recipient_id)

    # Persisted presence_mode=dnd must disable unsolicited match invitations regardless heartbeat expiry
    if settings.presence_mode == "dnd":
        raise _INVITES_DISABLED

    if settings.match_invites == "none":
        raise _INVITES_DISABLED
    elif settings.match_invites == "friends" and not is_friends:
        raise _INVITES_DISABLED

    return recipient


async def block_user(db: AsyncSession, blocker_id: int, target_login: str) -> None:
    target = await db.scalar(select(User).where(User.login == target_login.strip()))
    if target is None:
        raise _USER_NOT_FOUND
    if target.id == blocker_id:
        raise _CANNOT_BLOCK_SELF

    low_id, high_id = (blocker_id, target.id) if blocker_id < target.id else (target.id, blocker_id)
    await db.scalars(
        select(User)
        .where(User.id.in_([low_id, high_id]))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    await db.execute(
        delete(Friendship).where(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
        )
    )

    existing = await db.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == target.id,
        )
    )
    if existing is None:
        db.add(UserBlock(blocker_id=blocker_id, blocked_id=target.id))
    await db.flush()


async def unblock_user(db: AsyncSession, blocker_id: int, blocked_user_id: int) -> None:
    await db.execute(
        delete(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_user_id,
        )
    )
    await db.flush()


async def list_blocks(db: AsyncSession, blocker_id: int) -> list[User]:
    query = (
        select(User)
        .join(UserBlock, UserBlock.blocked_id == User.id)
        .where(UserBlock.blocker_id == blocker_id)
        .order_by(User.login.asc())
    )
    return list((await db.scalars(query)).all())


async def get_user_social_profile(
    db: AsyncSession, current_user: User, target_login: str
) -> dict[str, Any]:
    target = await db.scalar(select(User).where(User.login == target_login.strip()))
    if target is None:
        raise _USER_NOT_FOUND

    if target.id == current_user.id:
        presence, game_id = await get_user_presence_and_game(db, current_user.id)
        return {
            "id": target.id,
            "login": target.login,
            "relationship": "self",
            "blocked_by_me": False,
            "presence": presence,
            "game_id": game_id,
        }

    if target.is_banned:
        return {
            "id": target.id,
            "login": target.login,
            "relationship": "unavailable",
            "blocked_by_me": False,
            "presence": "offline",
            "game_id": None,
        }

    blocked_by_me = await db.scalar(
        select(UserBlock.id).where(
            UserBlock.blocker_id == current_user.id,
            UserBlock.blocked_id == target.id,
        )
    ) is not None

    blocked_by_them = await db.scalar(
        select(UserBlock.id).where(
            UserBlock.blocker_id == target.id,
            UserBlock.blocked_id == current_user.id,
        )
    ) is not None

    # Приоритет blocked_by_me над blocked_by_them: пользователь всегда должен видеть
    # relationship 'blocked', чтобы иметь возможность разблокировать контакт.
    if blocked_by_me:
        return {
            "id": target.id,
            "login": target.login,
            "relationship": "blocked",
            "blocked_by_me": True,
            "presence": "offline",
            "game_id": None,
        }

    if blocked_by_them:
        return {
            "id": target.id,
            "login": target.login,
            "relationship": "unavailable",
            "blocked_by_me": False,
            "presence": "offline",
            "game_id": None,
        }

    low_id, high_id = (
        (current_user.id, target.id)
        if current_user.id < target.id
        else (target.id, current_user.id)
    )
    friendship = await db.scalar(
        select(Friendship).where(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
        )
    )

    if friendship is not None:
        if friendship.status == "accepted":
            relationship = "friend"
        elif friendship.status == "pending":
            relationship = "outgoing" if friendship.requester_id == current_user.id else "incoming"
        else:
            relationship = "none"
    else:
        relationship = "none"

    if relationship == "friend":
        presence, game_id = await get_user_presence_and_game(db, target.id)
    else:
        presence = "offline"
        game_id = None

    return {
        "id": target.id,
        "login": target.login,
        "relationship": relationship,
        "blocked_by_me": False,
        "presence": presence,
        "game_id": game_id,
    }
