import secrets
import uuid
from datetime import timedelta
from typing import Annotated

import app.core.clock as clock
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.db import get_db
from app.models import ActivePlayer, Invite, User
from app.schemas.games import TimeControlIn
from app.services.games import create_game
from app.services.rolls import get_rng
from app.services.settings import get_setting

router = APIRouter(prefix="/api/v1", tags=["invites"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]

_INVITE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_INVITE_TTL = timedelta(minutes=10)


@router.post("/invites")
async def create_invite(body: TimeControlIn, user: UserDep, db: DbDep) -> dict:
    now = clock.now()
    time_controls = await get_setting(db, "time_controls")
    if body.time_control not in time_controls:
        raise AppError(400, "INVALID_TIME_CONTROL", "Недопустимый контроль времени")
    active = await db.get(ActivePlayer, user.id)
    if active is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")
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


@router.post("/invites/{code}/accept")
async def accept_invite(code: str, user: UserDep, db: DbDep) -> dict:
    now = clock.now()
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
    game = await create_game(db, invite.creator_id, user.id, invite.time_control, now)
    invite.game_id = game.id
    return {"game_id": str(game.id)}


@router.delete("/invites/{code}", status_code=204)
async def delete_invite(code: str, user: UserDep, db: DbDep) -> None:
    invite = await db.get(Invite, code)
    if invite is None or invite.creator_id != user.id:
        raise AppError(404, "INVITE_NOT_FOUND", "Инвайт не найден")
    if invite.game_id is not None:
        raise AppError(400, "INVITE_EXPIRED", "Инвайт недействителен")
    await db.delete(invite)
