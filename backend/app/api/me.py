from datetime import datetime
from typing import Annotated

import app.core.clock as clock
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.core.ratelimit import hit
from app.core.security import hash_password, verify_password
from app.core.sessions import revoke_all
from app.db import get_db
from app.models import ActivePlayer, Game, Ledger, User
from app.schemas.auth import LedgerItemOut, MeOut, Page, PasswordIn
from app.schemas.games import GameHistoryItem, GamesHistoryOut
from app.schemas.items import DailyRewardClaimOut, DailyRewardOut
from app.services.daily_reward import claim as claim_daily_reward
from app.services.daily_reward import get_status as get_daily_reward_status
from app.services.economy import lock_user

router = APIRouter(prefix="/api/v1", tags=["me"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


def me_out(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        login=user.login,
        role=user.role,
        balance=user.balance,
        elo=user.elo,
    )


@router.get("/me", response_model=MeOut)
async def read_me(user: UserDep, db: DbDep) -> MeOut:
    return me_out(user)


@router.get("/me/daily-reward", response_model=DailyRewardOut)
async def read_daily_reward(user: UserDep, db: DbDep) -> DailyRewardOut:
    return await get_daily_reward_status(db, user, clock.now())


@router.post("/me/daily-reward", response_model=DailyRewardClaimOut)
async def claim_daily_reward_endpoint(user: UserDep, db: DbDep) -> DailyRewardClaimOut:
    await hit(f"rl:items:{user.id}", 3, 1)
    return await claim_daily_reward(db, user, clock.now())


@router.post("/me/password", status_code=204)
async def change_password(
    body: PasswordIn, request: Request, user: UserDep, db: DbDep
) -> None:
    if not verify_password(user.password_hash, body.old_password):
        raise AppError(400, "WRONG_PASSWORD", "Неверный пароль")
    user.password_hash = hash_password(body.new_password)
    session_id = getattr(request.state, "session_id", None)
    await revoke_all(db, user.id, except_session_id=session_id)


@router.get("/me/active-game")
async def read_active_game(user: UserDep, db: DbDep) -> dict:
    active = await db.get(ActivePlayer, user.id)
    return {"game_id": str(active.game_id) if active is not None else None}


@router.get("/me/games", response_model=GamesHistoryOut)
async def read_games_history(
    user: UserDep,
    db: DbDep,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> GamesHistoryOut:
    query = select(Game).where(
        or_(Game.white_id == user.id, Game.black_id == user.id),
        Game.status.in_(("finished", "aborted")),
    )
    if before is not None:
        query = query.where(Game.finished_at < before)
    query = query.order_by(Game.finished_at.desc()).limit(limit)
    games = (await db.scalars(query)).all()
    user_ids: set[int] = set()
    for game in games:
        user_ids.update((game.white_id, game.black_id))
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()}
    items = []
    for game in games:
        if game.white_id == user.id:
            color, opponent_id = "white", game.black_id
            elo_delta = (
                game.white_elo_after - game.white_elo_before
                if game.white_elo_after is not None
                else None
            )
        else:
            color, opponent_id = "black", game.white_id
            elo_delta = (
                game.black_elo_after - game.black_elo_before
                if game.black_elo_after is not None
                else None
            )
        items.append(
            GameHistoryItem(
                id=str(game.id),
                opponent_login=users[opponent_id].login,
                color=color,
                result=game.result,
                end_reason=game.end_reason,
                time_control=game.time_control,
                finished_at=game.finished_at,
                elo_delta=elo_delta,
            )
        )
    next_before = items[-1].finished_at.isoformat() if items and len(items) == limit else None
    return GamesHistoryOut(items=items, next_before=next_before)


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
