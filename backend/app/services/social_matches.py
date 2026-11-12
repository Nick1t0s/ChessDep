import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.clock as clock
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.models import ActivePlayer, Game, Invite, User
from app.models.social import Friendship, InviteDelivery, Notification
from app.services.friends import accept_friend_request, delete_friend_request
from app.services.games import create_game, lock_game
from app.services.notifications import notify
from app.services.social_settings import ensure_invitation_allowed, ensure_not_blocked

_INVITE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_INVITE_TTL = timedelta(minutes=10)


async def accept_invite_domain(
    db: AsyncSession, code: str, user: User, now: datetime | None = None
) -> str:
    if now is None:
        now = clock.now()

    # Lock invite first
    invite = await db.scalar(
        select(Invite)
        .where(Invite.code == code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invite is None:
        raise AppError(404, "INVITE_NOT_FOUND", "Инвайт не найден")
    if invite.game_id is not None or invite.expires_at <= now:
        raise AppError(400, "INVITE_EXPIRED", "Инвайт недействителен")
    if invite.creator_id == user.id:
        raise AppError(400, "INVITE_OWN", "Нельзя принять свой инвайт")

    # Enforce targeted recipient if set
    if invite.target_user_id is not None and invite.target_user_id != user.id:
        raise AppError(403, "FORBIDDEN", "Этот инвайт предназначен другому игроку")

    # Enforce creator not banned
    creator = await db.get(User, invite.creator_id)
    if creator is None or creator.is_banned:
        raise AppError(403, "USER_BANNED", "Создатель инвайта заблокирован")

    # Enforce blocks both directions
    await ensure_not_blocked(db, user.id, invite.creator_id)

    # Enforce no active game for creator or user
    active_creator = await db.get(ActivePlayer, invite.creator_id)
    if active_creator is not None:
        raise AppError(409, "ALREADY_IN_GAME", "Создатель инвайта уже в партии")
    active_user = await db.get(ActivePlayer, user.id)
    if active_user is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")

    # Lock delivery: no declined delivery for this recipient
    delivery = await db.scalar(
        select(InviteDelivery)
        .where(InviteDelivery.code == code, InviteDelivery.recipient_id == user.id)
        .with_for_update()
    )
    if delivery is not None and delivery.status == "declined":
        raise AppError(400, "INVITE_DECLINED", "Приглашение было отклонено")

    game = await create_game(db, invite.creator_id, user.id, invite.time_control, now)
    invite.game_id = game.id

    if delivery is not None:
        delivery.status = "accepted"

    # Mark notification read for this user
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.kind == "match_invite")
        .where(
            or_(
                Notification.href == f"/invite.html?code={code}",
                Notification.href.like(f"%code={code}%"),
            )
        )
        .values(read=True)
    )

    return str(game.id)


async def decline_invite_domain(
    db: AsyncSession, code: str, user: User, now: datetime | None = None
) -> None:
    if now is None:
        now = clock.now()

    # Lock invite FIRST (consistent order to prevent deadlocks)
    invite = await db.scalar(
        select(Invite)
        .where(Invite.code == code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invite is None:
        raise AppError(404, "INVITE_NOT_FOUND", "Инвайт не найден")
    if invite.game_id is not None or invite.expires_at <= now:
        raise AppError(400, "INVITE_EXPIRED", "Инвайт недействителен")
    if invite.target_user_id is not None and invite.target_user_id != user.id:
        raise AppError(403, "FORBIDDEN", "Этот инвайт предназначен другому игроку")

    # Lock delivery SECOND
    delivery = await db.scalar(
        select(InviteDelivery)
        .where(InviteDelivery.code == code, InviteDelivery.recipient_id == user.id)
        .with_for_update()
    )
    if delivery is None:
        raise AppError(404, "INVITE_NOT_FOUND", "Приглашение не найдено")
    if delivery.status != "pending":
        raise AppError(400, "INVITE_ALREADY_HANDLED", "Приглашение уже обработано")

    delivery.status = "declined"

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.kind == "match_invite")
        .where(
            or_(
                Notification.href == f"/invite.html?code={code}",
                Notification.href.like(f"%code={code}%"),
            )
        )
        .values(read=True)
    )


async def create_rematch_domain(
    db: AsyncSession, game_id: uuid.UUID, user: User, now: datetime | None = None
) -> dict[str, Any]:
    if now is None:
        now = clock.now()

    # 1. Lock source game row
    game = await lock_game(db, game_id)
    if user.id not in (game.white_id, game.black_id):
        raise AppError(404, "GAME_NOT_FOUND", "Партия не найдена")

    if game.status != "finished":
        raise AppError(400, "GAME_NOT_FINISHED", "Реванш доступен только для завершённых партий")

    opponent_id = game.black_id if user.id == game.white_id else game.white_id

    # 2. Check creator active status FIRST
    active_creator = await db.get(ActivePlayer, user.id)
    if active_creator is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")

    # 3. Check opponent availability and active status FIRST
    opponent = await db.get(User, opponent_id)
    if opponent is None or opponent.is_banned:
        raise AppError(403, "USER_BANNED", "Соперник недоступен")

    active_opp = await db.get(ActivePlayer, opponent_id)
    if active_opp is not None:
        raise AppError(409, "ALREADY_IN_GAME", "Соперник уже в активной партии")

    # 4. Check policy, contact block, and DND FIRST
    await ensure_invitation_allowed(db, user.id, opponent_id, require_friendship=False)

    # 5. Check idempotent repeated live request (exclude declined delivery)
    live_invites = (
        await db.scalars(
            select(Invite)
            .where(
                Invite.source_game_id == game.id,
                Invite.creator_id == user.id,
                Invite.game_id.is_(None),
                Invite.expires_at > now,
            )
            .order_by(Invite.created_at.desc())
        )
    ).all()

    for live in live_invites:
        deliv = await db.scalar(
            select(InviteDelivery).where(
                InviteDelivery.code == live.code, InviteDelivery.recipient_id == opponent_id
            )
        )
        # If delivery was declined, do not reuse it; if pending, reuse idempotently
        if deliv is not None and deliv.status == "pending":
            return {"code": live.code, "expires_at": live.expires_at, "status": "sent"}

    # 6. Rate limit for creating a new request
    await hit(f"rl:rematch:{user.id}", 10, 60)

    # 7. Create targeted private invite
    code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(10))
    invite = Invite(
        code=code,
        creator_id=user.id,
        target_user_id=opponent_id,
        source_game_id=game.id,
        time_control=game.time_control,
        created_at=now,
        expires_at=now + _INVITE_TTL,
    )
    db.add(invite)
    await db.flush()

    # 8. Delivery status pending
    stmt = (
        pg_insert(InviteDelivery)
        .values(code=invite.code, recipient_id=opponent_id, status="pending")
        .on_conflict_do_nothing(index_elements=["code", "recipient_id"])
    )
    await db.execute(stmt)

    # 9. Notify match_invite
    await notify(
        db,
        user_id=opponent_id,
        kind="match_invite",
        title="Предложение реванша",
        body=f"{user.login} предлагает реванш ({invite.time_control})",
        href=f"/invite.html?code={invite.code}",
        now=now,
        data={
            "actor_id": user.id,
            "invite_code": invite.code,
            "source_game_id": str(game.id),
        },
    )

    return {"code": invite.code, "expires_at": invite.expires_at, "status": "sent"}


def _extract_invite_code(notification: Any) -> str | None:
    data = getattr(notification, "data", None) or {}
    if isinstance(data, dict) and "invite_code" in data:
        return str(data["invite_code"])
    href = getattr(notification, "href", None)
    if href and href.startswith("/invite.html?"):
        parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        if "code" in parsed and parsed["code"]:
            return parsed["code"][0]
    return None


async def _resolve_friend_actor_id(db: AsyncSession, notification: Any) -> int | None:
    data = getattr(notification, "data", None) or {}
    if isinstance(data, dict) and data.get("actor_id"):
        return int(data["actor_id"])
    href = getattr(notification, "href", None)
    if href and "/user.html" in href:
        parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        if "login" in parsed and parsed["login"]:
            login = parsed["login"][0].strip()
            user = await db.scalar(select(User).where(User.login == login))
            if user is not None:
                return user.id
    return None


async def notification_action_info(
    db: AsyncSession, user_id: int, notification: Any
) -> dict[str, Any]:
    kind = getattr(notification, "kind", None)
    if kind == "friend_request":
        actor_id = await _resolve_friend_actor_id(db, notification)
        if not actor_id or actor_id == user_id:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        low_id, high_id = (user_id, actor_id) if user_id < actor_id else (actor_id, user_id)
        friendship = await db.scalar(
            select(Friendship).where(
                Friendship.user_low_id == low_id, Friendship.user_high_id == high_id
            )
        )
        if friendship is None:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}
        if friendship.status == "accepted":
            return {"action_state": "accepted", "allowed_actions": [], "game_id": None}
        if friendship.status == "pending":
            if friendship.requester_id != actor_id:
                return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

            # Check if actor or recipient is blocked or banned
            try:
                await ensure_not_blocked(db, user_id, actor_id)
            except AppError:
                return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}
            requester = await db.get(User, actor_id)
            if requester is None or requester.is_banned:
                return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

            return {
                "action_state": "pending",
                "allowed_actions": ["accept", "decline"],
                "game_id": None,
            }
        return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

    if kind == "match_invite":
        code = _extract_invite_code(notification)
        if not code:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        delivery = await db.scalar(
            select(InviteDelivery).where(
                InviteDelivery.code == code, InviteDelivery.recipient_id == user_id
            )
        )
        delivery_status = getattr(delivery, "status", None) if delivery else None

        invite = await db.scalar(select(Invite).where(Invite.code == code))
        now = clock.now()

        if invite is None:
            if delivery_status == "declined":
                return {"action_state": "declined", "allowed_actions": [], "game_id": None}
            if delivery_status == "accepted":
                return {"action_state": "accepted", "allowed_actions": [], "game_id": None}
            return {"action_state": "cancelled", "allowed_actions": [], "game_id": None}

        # Check contact block
        try:
            await ensure_not_blocked(db, user_id, invite.creator_id)
        except AppError:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        # Check banned creator
        creator = await db.get(User, invite.creator_id)
        if creator is None or creator.is_banned:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        # Check active players for match invites: if creator or recipient is in active game -> unavailable
        active_creator = await db.get(ActivePlayer, invite.creator_id)
        active_user = await db.get(ActivePlayer, user_id)
        if active_creator is not None or active_user is not None:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        if invite.game_id is not None:
            game = await db.get(Game, invite.game_id)
            if game and user_id in (game.white_id, game.black_id):
                return {
                    "action_state": "accepted",
                    "allowed_actions": [],
                    "game_id": str(invite.game_id),
                }
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        if delivery_status == "declined":
            return {"action_state": "declined", "allowed_actions": [], "game_id": None}

        if invite.expires_at <= now:
            return {"action_state": "expired", "allowed_actions": [], "game_id": None}

        if invite.target_user_id is not None and invite.target_user_id != user_id:
            return {"action_state": "unavailable", "allowed_actions": [], "game_id": None}

        return {
            "action_state": "pending",
            "allowed_actions": ["accept", "decline"],
            "game_id": None,
        }

    return {"action_state": None, "allowed_actions": [], "game_id": None}


async def handle_notification_action(
    db: AsyncSession,
    notification_id: int,
    user: User,
    action: Literal["accept", "decline"],
    now: datetime | None = None,
) -> dict[str, Any]:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise AppError(404, "NOTIFICATION_NOT_FOUND", "Уведомление не найдено")

    # Authoritative notification action info check
    info = await notification_action_info(db, user.id, notification)
    if action not in info.get("allowed_actions", []):
        raise AppError(400, "ACTION_NOT_ALLOWED", "Действие недоступно")

    kind = notification.kind
    if kind == "friend_request":
        actor_id = await _resolve_friend_actor_id(db, notification)
        if not actor_id:
            raise AppError(400, "ACTION_NOT_ALLOWED", "Запрос в друзья не найден или недействителен")

        if action == "accept":
            await accept_friend_request(db, user, actor_id, now=now)
            notification.read = True
            return {"status": "accepted", "game_id": None}
        else:
            await delete_friend_request(db, user.id, actor_id)
            notification.read = True
            return {"status": "declined", "game_id": None}

    elif kind == "match_invite":
        code = _extract_invite_code(notification)
        if not code:
            raise AppError(400, "INVALID_INVITE", "Код приглашения не найден")

        if action == "accept":
            game_id = await accept_invite_domain(db, code, user, now=now)
            notification.read = True
            return {"status": "accepted", "game_id": game_id}
        else:
            await decline_invite_domain(db, code, user, now=now)
            notification.read = True
            return {"status": "declined", "game_id": None}

    raise AppError(400, "ACTION_NOT_ALLOWED", "Действие недоступно для этого типа уведомления")
