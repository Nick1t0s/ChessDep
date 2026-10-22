from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        body = value.strip()
        if not body or len(body) > 300:
            raise ValueError("Сообщение пустое или длиннее 300 символов")
        return body


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    login: str
    role: str
    body: str
    created_at: datetime


class ChatPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChatMessageOut]
    next_cursor: int | None
