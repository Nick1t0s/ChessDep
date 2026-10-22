from typing import Annotated, Literal

import app.core.clock as clock
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.ratelimit import hit
from app.db import get_db
from app.models import User
from app.schemas.gifts import GiftIn, GiftsPage, UnseenCountOut
from app.services import gifts as gifts_service

router = APIRouter(prefix="/api/v1", tags=["gifts"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.post("/gifts", status_code=201)
async def send_gift(body: GiftIn, user: UserDep, db: DbDep) -> dict:
    await hit(f"rl:gift:{user.id}", 10, 60)
    await gifts_service.send_gift(
        db, user, body.item_id, body.to_login, body.note, clock.now()
    )
    return {"ok": True}


@router.get("/me/gifts", response_model=GiftsPage)
async def my_gifts(
    user: UserDep,
    db: DbDep,
    direction: Literal["in", "out"] = "in",
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> GiftsPage:
    return await gifts_service.list_gifts(db, user, direction, before_id, limit)


@router.get("/me/gifts/unseen-count", response_model=UnseenCountOut)
async def gifts_unseen_count(user: UserDep, db: DbDep) -> UnseenCountOut:
    count = await gifts_service.unseen_count(db, user)
    return UnseenCountOut(count=count)
