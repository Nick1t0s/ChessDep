from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.leaderboard import LeaderboardEntryOut

router = APIRouter(prefix="/api/v1", tags=["leaderboard"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/leaderboard", response_model=list[LeaderboardEntryOut])
async def leaderboard(
    db: DbDep,
    by: Literal["elo", "balance"] = "elo",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[LeaderboardEntryOut]:
    field = User.elo if by == "elo" else User.balance
    rows = (
        await db.scalars(
            select(User)
            .where(User.is_banned.is_(False))
            .order_by(field.desc(), asc(User.id))
            .limit(limit)
        )
    ).all()
    return [
        LeaderboardEntryOut(
            rank=rank,
            login=user.login,
            elo=user.elo,
            balance=user.balance,
        )
        for rank, user in enumerate(rows, start=1)
    ]
