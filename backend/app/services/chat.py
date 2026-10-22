import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db import after_commit
from app.models import Game, GameMessage, User
from app.schemas.chat import ChatMessageOut, ChatPageOut
from app.services import pubsub

_GAME_NOT_FOUND = AppError(404, "GAME_NOT_FOUND", "Партия не найдена")


def role_of(game: Game, user_id: int) -> str:
    if user_id == game.white_id:
        return "white"
    if user_id == game.black_id:
        return "black"
    return "spectator"


def _message_out(message: GameMessage, users: dict[int, User], game: Game) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        login=users[message.user_id].login,
        role=role_of(game, message.user_id),
        body=message.body,
        created_at=message.created_at,
    )


async def post_message(
    db: AsyncSession, user: User, game_id: uuid.UUID, body: str
) -> ChatMessageOut:
    game = await db.get(Game, game_id)
    if game is None:
        raise _GAME_NOT_FOUND
    message = GameMessage(game_id=game_id, user_id=user.id, body=body)
    db.add(message)
    await db.flush()
    out = ChatMessageOut(
        id=message.id,
        login=user.login,
        role=role_of(game, user.id),
        body=message.body,
        created_at=message.created_at,
    )
    after_commit(
        db,
        lambda: pubsub.publish_game(game_id, {"chat": out.model_dump(mode="json")}),
    )
    return out


async def list_messages(
    db: AsyncSession, game_id: uuid.UUID, before_id: int | None, limit: int
) -> ChatPageOut:
    game = await db.get(Game, game_id)
    if game is None:
        raise _GAME_NOT_FOUND
    query = select(GameMessage).where(GameMessage.game_id == game_id)
    if before_id is not None:
        query = query.where(GameMessage.id < before_id)
    query = query.order_by(GameMessage.id.desc()).limit(limit)
    rows = (await db.scalars(query)).all()
    user_ids = {message.user_id for message in rows}
    users = {
        u.id: u
        for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
    }
    items = [_message_out(message, users, game) for message in reversed(rows)]
    next_cursor = items[0].id if len(items) == limit else None
    return ChatPageOut(items=items, next_cursor=next_cursor)
