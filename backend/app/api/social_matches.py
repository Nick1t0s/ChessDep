import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models.user import User
from app.services.social_matches import (
    create_rematch_domain,
    decline_invite_domain,
    handle_notification_action,
)

router = APIRouter(prefix="/api/v1", tags=["social_matches"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


class RematchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    expires_at: object
    status: str = "sent"


class NotificationActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "decline"]


class NotificationActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    game_id: str | None = None


@router.post("/games/{game_id}/rematch", response_model=RematchOut)
async def request_rematch(
    game_id: uuid.UUID,
    user: UserDep,
    db: DbDep,
) -> dict:
    return await create_rematch_domain(db, game_id, user)


@router.post("/invites/{code}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invite(
    code: str,
    user: UserDep,
    db: DbDep,
) -> Response:
    await decline_invite_domain(db, code, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/notifications/{notification_id}/action", response_model=NotificationActionOut
)
async def process_notification_action(
    notification_id: int,
    body: NotificationActionIn,
    user: UserDep,
    db: DbDep,
) -> dict:
    return await handle_notification_action(db, notification_id, user, body.action)
