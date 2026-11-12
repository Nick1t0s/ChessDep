from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db import get_db
from app.models.user import User
from app.schemas.social import (
    FriendRequestsOut,
    FriendRequestIn,
    FriendsListOut,
    FriendStatusOut,
    FriendUserOut,
    UserSearchListOut,
    UserSearchOut,
)
from app.services import friends as friends_service
from app.services import social_settings as social_settings_service

router = APIRouter(prefix="/api/v1", tags=["friends"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]


@router.get("/friends", response_model=FriendsListOut)
async def get_friends(user: UserDep, db: DbDep) -> FriendsListOut:
    friends = await friends_service.list_friends(db, user.id)
    friend_ids = [f.id for f in friends]
    presence_map = await social_settings_service.batch_get_presence(db, friend_ids)

    items = [
        FriendUserOut(
            id=f.id,
            login=f.login,
            elo=f.elo,
            presence=presence_map.get(f.id, ("offline", None))[0],  # type: ignore[arg-type]
            game_id=presence_map.get(f.id, ("offline", None))[1],
        )
        for f in friends
    ]
    return FriendsListOut(items=items)


@router.get("/friends/requests", response_model=FriendRequestsOut)
async def get_friend_requests(user: UserDep, db: DbDep) -> FriendRequestsOut:
    incoming, outgoing = await friends_service.list_friend_requests(db, user.id)
    return FriendRequestsOut(
        incoming=[FriendUserOut(id=u.id, login=u.login, elo=u.elo) for u in incoming],
        outgoing=[FriendUserOut(id=u.id, login=u.login, elo=u.elo) for u in outgoing],
    )


@router.post("/friends/requests", response_model=FriendStatusOut)
async def create_friend_request(
    body: FriendRequestIn,
    user: UserDep,
    db: DbDep,
) -> FriendStatusOut:
    result = await friends_service.send_friend_request(db, user, body.login)
    return FriendStatusOut(status=result["status"])


@router.post("/friends/requests/{user_id}/accept", response_model=FriendStatusOut)
async def accept_friend_request(
    user_id: int,
    user: UserDep,
    db: DbDep,
) -> FriendStatusOut:
    result = await friends_service.accept_friend_request(db, user, user_id)
    return FriendStatusOut(status=result["status"])


@router.delete("/friends/requests/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_friend_request(
    user_id: int,
    user: UserDep,
    db: DbDep,
) -> Response:
    await friends_service.delete_friend_request(db, user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/friends/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_friend(
    user_id: int,
    user: UserDep,
    db: DbDep,
) -> Response:
    await friends_service.remove_friend(db, user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/search", response_model=UserSearchListOut)
async def search_users(
    user: UserDep,
    db: DbDep,
    q: Annotated[str, Query(min_length=2, max_length=64)],
) -> UserSearchListOut:
    users = await friends_service.search_users(db, user.id, q)
    items = [
        UserSearchOut(
            id=int(u["id"]),
            login=str(u["login"]),
            elo=int(u["elo"]),
            relationship=u["relationship"],  # type: ignore[arg-type]
        )
        for u in users
    ]
    return UserSearchListOut(items=items)
