from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models.user import User
from app.schemas.social import (
    NotificationOut,
    NotificationsPageOut,
    UnreadCountOut,
)
from app.services import notifications as notifications_service

router = APIRouter(prefix="/api/v1", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.get("/notifications", response_model=NotificationsPageOut)
async def get_notifications(
    user: UserDep,
    db: DbDep,
    before_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotificationsPageOut:
    items, next_cursor, unread_count = await notifications_service.list_notifications(
        db,
        user.id,
        before_id=before_id,
        limit=limit,
    )
    return NotificationsPageOut(
        items=[NotificationOut.model_validate(n) for n in items],
        next_cursor=next_cursor,
        unread_count=unread_count,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def get_unread_count(
    user: UserDep,
    db: DbDep,
) -> UnreadCountOut:
    count = await notifications_service.get_unread_count(db, user.id)
    return UnreadCountOut(count=count)


@router.post("/notifications/{id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    id: int,
    user: UserDep,
    db: DbDep,
) -> Response:
    await notifications_service.mark_read(db, user.id, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    user: UserDep,
    db: DbDep,
) -> Response:
    await notifications_service.mark_all_read(db, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
