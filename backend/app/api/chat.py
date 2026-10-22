import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.ratelimit import hit
from app.db import get_db
from app.models import User
from app.schemas.chat import ChatIn, ChatMessageOut, ChatPageOut
from app.services import chat as chat_service

router = APIRouter(prefix="/api/v1", tags=["chat"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.post(
    "/games/{game_id}/chat", response_model=ChatMessageOut, status_code=201
)
async def post_message(
    game_id: uuid.UUID, body: ChatIn, user: UserDep, db: DbDep
) -> ChatMessageOut:
    await hit(f"rl:chat:{user.id}", 1, 1)
    await hit(f"rl:chatm:{user.id}", 20, 60)
    return await chat_service.post_message(db, user, game_id, body.body)


@router.get("/games/{game_id}/chat", response_model=ChatPageOut)
async def list_messages(
    game_id: uuid.UUID,
    user: UserDep,
    db: DbDep,
    before_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChatPageOut:
    return await chat_service.list_messages(db, game_id, before_id, limit)
