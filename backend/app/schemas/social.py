from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class FriendUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    elo: int
    presence: Literal["online", "offline", "in_game", "dnd"] = "offline"
    game_id: str | None = None


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
    data: dict[str, Any] = Field(default_factory=dict)
    action_state: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    game_id: str | None = None


class NotificationsPageOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: int | None = None
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int


DEFAULT_NOTIFICATION_SETTINGS: dict[str, bool] = {
    "friend_request": True,
    "friend_accepted": True,
    "match_invite": True,
    "market_sale": True,
    "gift": True,
}


class SocialSettingsOut(BaseModel):
    presence_mode: Literal["online", "dnd"]
    match_invites: Literal["all", "friends", "none"]
    notifications: dict[str, bool]


class SocialSettingsUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presence_mode: Literal["online", "dnd"] | None = None
    match_invites: Literal["all", "friends", "none"] | None = None
    notifications: dict[str, StrictBool] | None = None

    @field_validator("notifications")
    @classmethod
    def validate_notifications(cls, v: dict[str, StrictBool] | None) -> dict[str, StrictBool] | None:
        if v is None:
            return None
        allowed = {"friend_request", "friend_accepted", "match_invite", "market_sale", "gift"}
        for k, val in v.items():
            if k not in allowed:
                raise ValueError(f"Unknown notification key: {k}")
            if not isinstance(val, bool):
                raise ValueError(f"Value for {k} must be a literal boolean")
        return v


class PresenceIn(BaseModel):
    presence: Literal["online", "dnd"] | None = None


class PresenceOut(BaseModel):
    presence: Literal["online", "dnd"]


class BlockUserIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)


class BlockedUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    elo: int


class BlockedListOut(BaseModel):
    items: list[BlockedUserOut]


class UserSocialOut(BaseModel):
    id: int
    login: str
    relationship: Literal["self", "none", "friend", "incoming", "outgoing", "blocked", "unavailable"]
    blocked_by_me: bool
    presence: Literal["online", "offline", "in_game", "dnd"]
    game_id: str | None = None
