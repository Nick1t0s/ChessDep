import secrets
from datetime import timedelta
from typing import Annotated

import app.core.clock as clock
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.db import get_db
from app.models import ActivePlayer, Invite, User
from app.models.social import InviteDelivery
from app.schemas.games import TimeControlIn
from app.services.friends import require_friend
from app.services.items import ensure_loadout_complete
from app.services.notifications import notify
from app.services.settings import get_setting
from app.services.social_matches import accept_invite_domain
from app.services.social_settings import ensure_invitation_allowed

router = APIRouter(prefix="/api/v1", tags=["invites"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]

_INVITE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_INVITE_TTL = timedelta(minutes=10)


class SendInviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    friend_id: int


@router.post("/invites")
async def create_invite(body: TimeControlIn, user: UserDep, db: DbDep) -> dict:
    now = clock.now()
    time_controls = await get_setting(db, "time_controls")
    if body.time_control not in time_controls:
        raise AppError(400, "INVALID_TIME_CONTROL", "Недопустимый контроль времени")
    active = await db.get(ActivePlayer, user.id)
    if active is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")
    await ensure_loadout_complete(db, user.id)
    code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(10))
    invite = Invite(
        code=code,
        creator_id=user.id,
        time_control=body.time_control,
        created_at=now,
        expires_at=now + _INVITE_TTL,
    )
    db.add(invite)
    return {"code": code, "expires_at": invite.expires_at}


@router.post("/invites/{code}/send")
async def send_invite(
    code: str, body: SendInviteIn, user: UserDep, db: DbDep
) -> dict:
    now = clock.now()
    # 1. Захватываем блокировку инвайта до любых проверок
    invite = await db.scalar(
        select(Invite)
        .where(Invite.code == code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # Не утекаем информацию о существовании инвайта неавторизованным пользователям
    if invite is None or invite.creator_id != user.id:
        raise AppError(404, "INVITE_NOT_FOUND", "Инвайт не найден")

    if invite.game_id is not None or invite.expires_at <= now:
        raise AppError(400, "INVITE_EXPIRED", "Инвайт недействителен")
    if invite.target_user_id is not None and invite.target_user_id != body.friend_id:
        raise AppError(403, "FORBIDDEN", "Это приглашение предназначено другому игроку")

    # 2. Проверяем, что создатель инвайта сам не находится в активной партии
    active_creator = await db.get(ActivePlayer, user.id)
    if active_creator is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")

    # 4. Проверяем дружбу (отклоняет чужих, заблокированных, себя)
    recipient = await require_friend(db, user.id, body.friend_id)

    # Проверяем политику приглашений и блокировок
    await ensure_invitation_allowed(db, user.id, recipient.id, require_friendship=True)

    # 5. Проверяем, что получатель не в активной партии
    active_recipient = await db.get(ActivePlayer, recipient.id)
    if active_recipient is not None:
        raise AppError(409, "ALREADY_IN_GAME", "Игрок уже в партии")

    # 6. Идемпотентная доставка через pg_insert on_conflict_do_nothing
    stmt = (
        pg_insert(InviteDelivery)
        .values(code=invite.code, recipient_id=recipient.id, status="pending")
        .on_conflict_do_nothing(index_elements=["code", "recipient_id"])
    )
    res = await db.execute(stmt)

    # 7. Умеренный rate limit и уведомление применяются только при реальной новой отправке
    if res.rowcount and res.rowcount > 0:
        await hit(f"rl:invite:send:{user.id}", 20, 60)
        await notify(
            db,
            user_id=recipient.id,
            kind="match_invite",
            title="Приглашение в игру",
            body=f"{user.login} приглашает вас сыграть партию ({invite.time_control})",
            href=f"/invite.html?code={invite.code}",
            now=now,
            data={"actor_id": user.id, "invite_code": invite.code},
        )

    return {"status": "sent"}


@router.post("/invites/{code}/accept")
async def accept_invite(code: str, user: UserDep, db: DbDep) -> dict:
    game_id = await accept_invite_domain(db, code, user)
    return {"game_id": game_id}


@router.delete("/invites/{code}", status_code=204)
async def cancel_invite(code: str, user: UserDep, db: DbDep) -> None:
    invite = await db.scalar(
        select(Invite)
        .where(Invite.code == code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invite is None or invite.creator_id != user.id:
        raise AppError(404, "INVITE_NOT_FOUND", "Инвайт не найден")
    if invite.game_id is not None:
        raise AppError(400, "INVITE_EXPIRED", "Инвайт недействителен")
    await db.delete(invite)
