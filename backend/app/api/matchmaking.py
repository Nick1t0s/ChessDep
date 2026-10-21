from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas.games import TimeControlIn
from app.services import matchmaking

router = APIRouter(prefix="/api/v1", tags=["matchmaking"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.post("/matchmaking/queue", status_code=202)
async def join_queue(body: TimeControlIn, user: UserDep, db: DbDep) -> dict:
    await matchmaking.enqueue(db, user, body.time_control)
    return {"status": "queued"}


@router.delete("/matchmaking/queue", status_code=204)
async def leave_queue(user: UserDep) -> None:
    await matchmaking.dequeue(user)


@router.get("/matchmaking/status")
async def matchmaking_status(user: UserDep, db: DbDep) -> dict:
    return await matchmaking.status(db, user)
