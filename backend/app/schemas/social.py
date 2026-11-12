from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FriendUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    elo: int


class FriendsListOut(BaseModel):
    items: list[FriendUserOut]


class FriendRequestsOut(BaseModel):
    incoming: list[FriendUserOut]
    outgoing: list[FriendUserOut]


class UserSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    elo: int
    relationship: Literal["none", "friend", "incoming", "outgoing"]


class UserSearchListOut(BaseModel):
    items: list[UserSearchOut]


class FriendRequestIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)


class FriendStatusOut(BaseModel):
    status: Literal["pending", "accepted"]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    href: str | None = None
    read: bool
    created_at: datetime


class NotificationsPageOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: int | None = None
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int
