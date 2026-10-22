import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.errors import AppError
from app.db import get_db
from app.models import Game, User
from app.schemas.games import GamesHistoryOut
from app.schemas.history import GameEventsOut, ProfileOut
from app.services import history

router = APIRouter(prefix="/api/v1", tags=["game_history"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]

_GAME_NOT_FOUND = AppError(404, "GAME_NOT_FOUND", "Партия не найдена")


@router.get("/games/{game_id}/events", response_model=GameEventsOut)
async def get_game_events(
    game_id: uuid.UUID,
    *,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    user: UserDep,
    db: DbDep,
) -> GameEventsOut:
    game = await db.get(Game, game_id)
    if game is None:
        raise _GAME_NOT_FOUND
    data = await history.game_events(db, game, after_seq)
    return GameEventsOut.model_validate(data)


@router.get("/users/{login}", response_model=ProfileOut)
async def get_user_profile(login: str, user: UserDep, db: DbDep) -> ProfileOut:
    data = await history.user_profile(db, login)
    return ProfileOut.model_validate(data)


@router.get("/users/{login}/games", response_model=GamesHistoryOut)
async def get_user_games(
    login: str,
    *,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    user: UserDep,
    db: DbDep,
) -> GamesHistoryOut:
    profile_user = await history.user_by_login(db, login)
    data = await history.user_games(db, profile_user, before, limit)
    return GamesHistoryOut.model_validate(data)
