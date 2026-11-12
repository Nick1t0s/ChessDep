from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models.user import User
from app.schemas.social import (
    BlockedListOut,
    BlockedUserOut,
    BlockUserIn,
    PresenceIn,
    PresenceOut,
    SocialSettingsOut,
    SocialSettingsUpdateIn,
    UserSocialOut,
)
from app.services import social_settings as social_settings_service

router = APIRouter(prefix="/api/v1", tags=["social_settings"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.get("/me/social-settings", response_model=SocialSettingsOut)
async def get_my_social_settings(
    user: UserDep,
    db: DbDep,
) -> SocialSettingsOut:
    settings = await social_settings_service.get_social_settings(db, user.id)
    return SocialSettingsOut(**settings)


@router.patch("/me/social-settings", response_model=SocialSettingsOut)
async def patch_my_social_settings(
    body: SocialSettingsUpdateIn,
    user: UserDep,
    db: DbDep,
) -> SocialSettingsOut:
    settings = await social_settings_service.update_social_settings(
        db,
        user.id,
        presence_mode=body.presence_mode,
        match_invites=body.match_invites,
        notifications=body.notifications,
    )
    return SocialSettingsOut(**settings)


@router.post("/me/presence", response_model=PresenceOut)
async def update_presence(
    user: UserDep,
    db: DbDep,
    body: PresenceIn | None = None,
) -> PresenceOut:
    mode = await social_settings_service.record_presence_heartbeat(
        db,
        user.id,
        presence_mode=body.presence if body else None,
    )
    return PresenceOut(presence=mode)  # type: ignore[arg-type]


@router.get("/me/blocks", response_model=BlockedListOut)
async def get_my_blocks(
    user: UserDep,
    db: DbDep,
) -> BlockedListOut:
    users = await social_settings_service.list_blocks(db, user.id)
    items = [BlockedUserOut(id=u.id, login=u.login, elo=u.elo) for u in users]
    return BlockedListOut(items=items)


@router.post("/me/blocks", status_code=status.HTTP_204_NO_CONTENT)
async def create_block(
    body: BlockUserIn,
    user: UserDep,
    db: DbDep,
) -> Response:
    await social_settings_service.block_user(db, user.id, body.login)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_block(
    user_id: int,
    user: UserDep,
    db: DbDep,
) -> Response:
    await social_settings_service.unblock_user(db, user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{login}/social", response_model=UserSocialOut)
async def get_user_social(
    login: str,
    user: UserDep,
    db: DbDep,
) -> UserSocialOut:
    profile = await social_settings_service.get_user_social_profile(db, user, login)
    return UserSocialOut(**profile)
