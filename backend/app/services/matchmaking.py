from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db import SessionLocal
from app.models import ActivePlayer, Game
from app.redis import redis_client
from app.services.games import create_game
from app.services.settings import get_setting

_QUEUE_TTL_S = 10

_INVALID_TIME_CONTROL = AppError(400, "INVALID_TIME_CONTROL", "Недопустимый контроль времени")


def _user_key(user_id: int) -> str:
    return f"mm:user:{user_id}"


def _queue_key(tc: str) -> str:
    return f"mm:queue:{tc}"


async def enqueue(db: AsyncSession, user, tc: str) -> None:
    time_controls = await get_setting(db, "time_controls")
    if tc not in time_controls:
        raise _INVALID_TIME_CONTROL
    active = await db.get(ActivePlayer, user.id)
    if active is not None:
        raise AppError(409, "ALREADY_IN_GAME", "У вас уже есть активная партия")
    if await redis_client.get(_user_key(user.id)) is not None:
        # Уже в очереди: продлить heartbeat, не дублировать в списке.
        await redis_client.expire(_user_key(user.id), _QUEUE_TTL_S)
        return
    await redis_client.set(_user_key(user.id), tc, ex=_QUEUE_TTL_S)
    await redis_client.rpush(_queue_key(tc), str(user.id))


async def dequeue(user) -> None:
    tc = await redis_client.get(_user_key(user.id))
    if tc is None:
        return
    await redis_client.lrem(_queue_key(tc), 0, str(user.id))
    await redis_client.delete(_user_key(user.id))


async def status(db: AsyncSession, user) -> dict:
    active = await db.get(ActivePlayer, user.id)
    if active is not None:
        game = await db.get(Game, active.game_id)
        return {"status": "matched", "time_control": game.time_control, "game_id": str(game.id)}
    tc = await redis_client.get(_user_key(user.id))
    if tc is not None:
        await redis_client.expire(_user_key(user.id), _QUEUE_TTL_S)
        return {"status": "queued", "time_control": tc, "game_id": None}
    return {"status": "idle", "time_control": None, "game_id": None}


async def _pop_live(queue_key: str, tc: str) -> str | None:
    while True:
        user_id = await redis_client.lpop(queue_key)
        if user_id is None:
            return None
        if await redis_client.get(_user_key(int(user_id))) == tc:
            return user_id
        # Игрок сбежал или его heartbeat истёк — пропускаем.


async def _in_game_ids(user_ids: list[int]) -> set[int]:
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(ActivePlayer.user_id).where(ActivePlayer.user_id.in_(user_ids))
            )
        ).all()
    return set(rows)


async def _match_pair(a: str, b: str, tc: str, now: datetime, queue_key: str) -> None:
    try:
        async with SessionLocal() as db:
            async with db.begin():
                await create_game(db, int(a), int(b), tc, now)
    except AppError as exc:
        if exc.code != "ALREADY_IN_GAME":
            raise
        # Откат уже произошёл. Кто-то из пары уже в партии.
        in_game = await _in_game_ids([int(a), int(b)])
        for user_id in (a, b):
            if int(user_id) in in_game:
                await redis_client.delete(_user_key(int(user_id)))
            else:
                await redis_client.lpush(queue_key, user_id)
        return
    # Пара создана.
    await redis_client.delete(_user_key(int(a)), _user_key(int(b)))


async def tick(now: datetime) -> None:
    async with SessionLocal() as db:
        time_controls = list(await get_setting(db, "time_controls"))
    for tc in time_controls:
        queue_key = _queue_key(tc)
        while await redis_client.llen(queue_key) >= 2:
            a = await _pop_live(queue_key, tc)
            if a is None:
                break
            b = await _pop_live(queue_key, tc)
            if b is None:
                await redis_client.lpush(queue_key, a)
                break
            await _match_pair(a, b, tc, now, queue_key)
