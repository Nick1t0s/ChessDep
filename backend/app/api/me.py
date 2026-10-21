from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.core.sessions import revoke_all
from app.db import get_db
from app.models import Ledger, User
from app.schemas.auth import DailyBonusOut, LedgerItemOut, MeOut, Page, PasswordIn
from app.services.economy import apply_delta, lock_user
from app.services.settings import get_setting

router = APIRouter(prefix="/api/v1", tags=["me"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


def daily_bonus_available_at(
    last_daily_bonus_at: datetime | None, cooldown_h: int
) -> datetime | None:
    if last_daily_bonus_at is None:
        return None
    available_at = last_daily_bonus_at + timedelta(hours=cooldown_h)
    if available_at <= datetime.now(UTC):
        return None
    return available_at


def me_out(user: User, cooldown_h: int) -> MeOut:
    return MeOut(
        id=user.id,
        login=user.login,
        role=user.role,
        balance=user.balance,
        elo=user.elo,
        daily_bonus_available_at=daily_bonus_available_at(
            user.last_daily_bonus_at, cooldown_h
        ),
    )


@router.get("/me", response_model=MeOut)
async def read_me(user: UserDep, db: DbDep) -> MeOut:
    cooldown_h = int(await get_setting(db, "daily_bonus_cooldown_h"))
    return me_out(user, cooldown_h)


@router.post("/me/password", status_code=204)
async def change_password(
    body: PasswordIn, request: Request, user: UserDep, db: DbDep
) -> None:
    if not verify_password(user.password_hash, body.old_password):
        raise AppError(400, "WRONG_PASSWORD", "Неверный пароль")
    user.password_hash = hash_password(body.new_password)
    session_id = getattr(request.state, "session_id", None)
    await revoke_all(db, user.id, except_session_id=session_id)


@router.post("/me/daily-bonus", response_model=DailyBonusOut)
async def daily_bonus(user: UserDep, db: DbDep) -> DailyBonusOut:
    cooldown_h = int(await get_setting(db, "daily_bonus_cooldown_h"))
    bonus = int(await get_setting(db, "daily_bonus"))
    now = datetime.now(UTC)
    locked = await lock_user(db, user.id)
    if locked.last_daily_bonus_at is not None:
        available_at = locked.last_daily_bonus_at + timedelta(hours=cooldown_h)
        if available_at > now:
            raise AppError(400, "BONUS_COOLDOWN", "Бонус ещё не готов")
    new_balance = await apply_delta(db, locked.id, bonus, "daily_bonus")
    locked.last_daily_bonus_at = now
    return DailyBonusOut(balance=new_balance, next_available_at=now + timedelta(hours=cooldown_h))


@router.get("/me/ledger", response_model=Page[LedgerItemOut])
async def read_ledger(
    user: UserDep,
    db: DbDep,
    cursor: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[LedgerItemOut]:
    query = select(Ledger).where(Ledger.user_id == user.id)
    if cursor is not None:
        query = query.where(Ledger.id < cursor)
    query = query.order_by(Ledger.id.desc()).limit(limit)
    rows = (await db.scalars(query)).all()
    items = [
        LedgerItemOut(
            id=row.id,
            delta=row.delta,
            balance_after=row.balance_after,
            reason=row.reason,
            ref=row.ref,
            created_at=row.created_at,
        )
        for row in rows
    ]
    next_cursor = items[-1].id if len(items) == limit else None
    return Page[LedgerItemOut](items=items, next_cursor=next_cursor)
