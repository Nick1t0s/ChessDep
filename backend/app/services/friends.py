from datetime import datetime
from typing import Literal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.clock as clock
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.models.social import Friendship, UserBlock
from app.models.user import User
from app.services.notifications import notify
from app.services.social_settings import ensure_not_blocked

_USER_NOT_FOUND = AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
_CANNOT_FRIEND_SELF = AppError(400, "CANNOT_FRIEND_SELF", "Нельзя добавить в друзья себя")
_USER_BANNED = AppError(403, "USER_BANNED", "Пользователь заблокирован")
_FRIEND_NOT_FOUND = AppError(404, "FRIEND_NOT_FOUND", "Пользователь не найден в друзьях")
_REQUEST_NOT_FOUND = AppError(404, "REQUEST_NOT_FOUND", "Запрос в друзья не найден")
_ALREADY_FRIENDS = AppError(409, "ALREADY_FRIENDS", "Пользователь уже в друзьях")
_REQUEST_ALREADY_SENT = AppError(409, "REQUEST_ALREADY_SENT", "Запрос уже отправлен")
_CROSS_REQUEST_EXISTS = AppError(
    409,
    "CROSS_REQUEST_EXISTS",
    "У вас есть входящий запрос от этого пользователя, примите его",
)
_ONLY_RECIPIENT_CAN_ACCEPT = AppError(
    403,
    "FORBIDDEN",
    "Только получатель может принять запрос в друзья",
)
_RATE_LIMITED = AppError(429, "RATE_LIMITED", "Слишком много запросов в друзья, подождите минуту")


def escape_like(s: str) -> str:
    """Экранирует спецсимволы LIKE/ILIKE для точного подстрочного поиска."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def require_friend(db: AsyncSession, user_id: int, friend_id: int) -> User:
    """Проверяет дружбу между user_id и friend_id; отклоняет self/nonfriend/banned."""
    if user_id == friend_id:
        raise _CANNOT_FRIEND_SELF

    friend = await db.get(User, friend_id)
    if friend is None:
        raise _USER_NOT_FOUND
    if friend.is_banned:
        raise _USER_BANNED

    low_id, high_id = (user_id, friend_id) if user_id < friend_id else (friend_id, user_id)
    friendship = await db.scalar(
        select(Friendship).where(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
            Friendship.status == "accepted",
        )
    )
    if friendship is None:
        raise _FRIEND_NOT_FOUND

    return friend


async def _lock_user_pair(db: AsyncSession, u1: int, u2: int) -> tuple[User, User]:
    """Блокирует строки двух пользователей в строго возрастающем порядке id."""
    if u1 == u2:
        raise _CANNOT_FRIEND_SELF

    low_id, high_id = (u1, u2) if u1 < u2 else (u2, u1)
    res = await db.scalars(
        select(User)
        .where(User.id.in_([low_id, high_id]))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    users = {u.id: u for u in res.all()}
    if low_id not in users or high_id not in users:
        raise _USER_NOT_FOUND
    return users[u1], users[u2]


async def list_friends(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = 250,
) -> list[User]:
    """Возвращает принятых друзей пользователя, отсортированных по логину."""
    limit = max(1, min(limit, 500))
    other_id_expr = case(
        (Friendship.user_low_id == user_id, Friendship.user_high_id),
        else_=Friendship.user_low_id,
    )
    query = (
        select(User)
        .join(
            Friendship,
            and_(
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
                Friendship.status == "accepted",
                other_id_expr == User.id,
            ),
        )
        .where(User.is_banned.is_(False))
        .order_by(User.login.asc())
        .limit(limit)
    )
    return list((await db.scalars(query)).all())


async def list_friend_requests(
    db: AsyncSession,
    user_id: int,
) -> tuple[list[User], list[User]]:
    """Возвращает входящие и исходящие заявки в друзья."""
    incoming_query = (
        select(User)
        .join(
            Friendship,
            and_(
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
                Friendship.status == "pending",
                Friendship.requester_id != user_id,
                Friendship.requester_id == User.id,
            ),
        )
        .where(User.is_banned.is_(False))
        .order_by(Friendship.created_at.desc())
    )
    incoming = list((await db.scalars(incoming_query)).all())

    other_id_expr = case(
        (Friendship.user_low_id == user_id, Friendship.user_high_id),
        else_=Friendship.user_low_id,
    )
    outgoing_query = (
        select(User)
        .join(
            Friendship,
            and_(
                or_(Friendship.user_low_id == user_id, Friendship.user_high_id == user_id),
                Friendship.status == "pending",
                Friendship.requester_id == user_id,
                other_id_expr == User.id,
            ),
        )
        .where(User.is_banned.is_(False))
        .order_by(Friendship.created_at.desc())
    )
    outgoing = list((await db.scalars(outgoing_query)).all())

    return incoming, outgoing


async def search_users(
    db: AsyncSession,
    current_user_id: int,
    query_text: str,
    *,
    limit: int = 20,
) -> list[dict[str, object]]:
    """Поиск пользователей по логину без себя, заблокированных и заблокировавших."""
    q = query_text.strip()
    if len(q) < 2 or len(q) > 64:
        raise AppError(422, "VALIDATION_ERROR", "Длина запроса от 2 до 64 символов")

    escaped = escape_like(q)
    limit = max(1, min(limit, 20))

    blocked_by_me = select(UserBlock.blocked_id).where(UserBlock.blocker_id == current_user_id)
    blocked_me = select(UserBlock.blocker_id).where(UserBlock.blocked_id == current_user_id)

    query = (
        select(User)
        .where(
            User.id != current_user_id,
            User.is_banned.is_(False),
            User.id.not_in(blocked_by_me),
            User.id.not_in(blocked_me),
            User.login.ilike(f"%{escaped}%", escape="\\"),
        )
        .order_by(User.login.asc())
        .limit(limit)
    )
    users = list((await db.scalars(query)).all())
    if not users:
        return []

    target_ids = [u.id for u in users]
    friendships_query = select(Friendship).where(
        or_(
            and_(Friendship.user_low_id == current_user_id, Friendship.user_high_id.in_(target_ids)),
            and_(Friendship.user_high_id == current_user_id, Friendship.user_low_id.in_(target_ids)),
        )
    )
    friendships = list((await db.scalars(friendships_query)).all())

    rel_map: dict[int, Literal["none", "friend", "incoming", "outgoing"]] = {}
    for f in friendships:
        other_id = f.user_high_id if f.user_low_id == current_user_id else f.user_low_id
        if f.status == "accepted":
            rel_map[other_id] = "friend"
        elif f.status == "pending":
            if f.requester_id == current_user_id:
                rel_map[other_id] = "outgoing"
            else:
                rel_map[other_id] = "incoming"

    result: list[dict[str, object]] = []
    for u in users:
        result.append(
            {
                "id": u.id,
                "login": u.login,
                "elo": u.elo,
                "relationship": rel_map.get(u.id, "none"),
            }
        )
    return result


async def send_friend_request(
    db: AsyncSession,
    current_user: User,
    target_login: str,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Отправляет заявку в друзья по логину пользователя."""
    target_user = await db.scalar(select(User).where(User.login == target_login.strip()))
    if target_user is None:
        raise _USER_NOT_FOUND
    if target_user.id == current_user.id:
        raise _CANNOT_FRIEND_SELF
    if target_user.is_banned:
        raise _USER_BANNED

    await ensure_not_blocked(db, current_user.id, target_user.id)

    # Резерв рейт-лимита
    await hit(f"friend_req:{current_user.id}", 30, 60)

    # Сериализация через блокировку пары пользователей в возрастающем порядке
    await _lock_user_pair(db, current_user.id, target_user.id)
    await ensure_not_blocked(db, current_user.id, target_user.id)

    low_id, high_id = (
        (current_user.id, target_user.id)
        if current_user.id < target_user.id
        else (target_user.id, current_user.id)
    )

    friendship = await db.scalar(
        select(Friendship)
        .where(Friendship.user_low_id == low_id, Friendship.user_high_id == high_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if friendship is not None:
        if friendship.status == "accepted":
            raise _ALREADY_FRIENDS
        if friendship.status == "pending":
            if friendship.requester_id == current_user.id:
                raise _REQUEST_ALREADY_SENT
            raise _CROSS_REQUEST_EXISTS

    if now is None:
        now = clock.now()

    new_friendship = Friendship(
        user_low_id=low_id,
        user_high_id=high_id,
        requester_id=current_user.id,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(new_friendship)
    await db.flush()

    await notify(
        db,
        user_id=target_user.id,
        kind="friend_request",
        title="Запрос в друзья",
        body=f"{current_user.login} хочет добавить вас в друзья",
        href="/friends.html",
        data={"actor_id": current_user.id, "friendship_id": new_friendship.id},
        now=now,
    )

    return {"status": "pending"}


async def accept_friend_request(
    db: AsyncSession,
    current_user: User,
    requester_user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Принимает входящую заявку в друзья; доступно только получателю."""
    if requester_user_id == current_user.id:
        raise _CANNOT_FRIEND_SELF

    await ensure_not_blocked(db, current_user.id, requester_user_id)

    _curr, requester_user = await _lock_user_pair(db, current_user.id, requester_user_id)
    if requester_user.is_banned:
        raise _USER_BANNED

    await ensure_not_blocked(db, current_user.id, requester_user_id)

    low_id, high_id = (
        (current_user.id, requester_user_id)
        if current_user.id < requester_user_id
        else (requester_user_id, current_user.id)
    )

    friendship = await db.scalar(
        select(Friendship)
        .where(Friendship.user_low_id == low_id, Friendship.user_high_id == high_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if friendship is None:
        raise _REQUEST_NOT_FOUND
    if friendship.status == "accepted":
        raise _ALREADY_FRIENDS

    recipient_id = (
        friendship.user_high_id
        if friendship.requester_id == friendship.user_low_id
        else friendship.user_low_id
    )
    if current_user.id != recipient_id:
        raise _ONLY_RECIPIENT_CAN_ACCEPT

    if now is None:
        now = clock.now()

    friendship.status = "accepted"
    friendship.updated_at = now
    await db.flush()

    await notify(
        db,
        user_id=requester_user_id,
        kind="friend_accepted",
        title="Запрос в друзья принят",
        body=f"{current_user.login} принял(а) вашу заявку в друзья",
        href=f"/user.html?login={current_user.login}",
        data={"actor_id": current_user.id},
        now=now,
    )

    return {"status": "accepted"}


async def delete_friend_request(
    db: AsyncSession,
    current_user_id: int,
    other_user_id: int,
) -> None:
    if current_user_id == other_user_id:
        raise _CANNOT_FRIEND_SELF

    low_id, high_id = (
        (current_user_id, other_user_id)
        if current_user_id < other_user_id
        else (other_user_id, current_user_id)
    )

    friendship = await db.scalar(
        select(Friendship)
        .where(Friendship.user_low_id == low_id, Friendship.user_high_id == high_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if friendship is None or friendship.status != "pending":
        raise _REQUEST_NOT_FOUND

    await db.delete(friendship)
    await db.flush()


async def remove_friend(
    db: AsyncSession,
    current_user_id: int,
    friend_id: int,
) -> None:
    if current_user_id == friend_id:
        raise _CANNOT_FRIEND_SELF

    low_id, high_id = (
        (current_user_id, friend_id)
        if current_user_id < friend_id
        else (friend_id, current_user_id)
    )

    friendship = await db.scalar(
        select(Friendship)
        .where(Friendship.user_low_id == low_id, Friendship.user_high_id == high_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if friendship is None or friendship.status != "accepted":
        raise _FRIEND_NOT_FOUND

    await db.delete(friendship)
    await db.flush()
